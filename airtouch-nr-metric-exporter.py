"""
A Python application to continuously monitor an AirTouch 5 controller
and send telemetry to New Relic using the modern OpenTelemetry SDK.

Final version: sends a single metric 'airtouch.zone.temperature' with a
comprehensive set of AC and Zone states as attributes.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict

# Used to load the .env file
from dotenv import load_dotenv

# PyAirtouch library and necessary enums
import pyairtouch
from pyairtouch import ZoneControlMethod, ZonePowerState

# --- OpenTelemetry Imports ---
# The modern, standard way to send telemetry data
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# --- Configuration ---
load_dotenv()
NEW_RELIC_KEY = os.getenv("NEW_RELIC_LICENSE_KEY")
# --- End Configuration ---


def setup_opentelemetry() -> metrics.Meter:
    """Configures and starts the OpenTelemetry SDK to send metrics to New Relic."""
    if not NEW_RELIC_KEY:
        raise ValueError("NEW_RELIC_LICENSE_KEY not found in environment variables.")

    # The OTLP endpoint for New Relic's US data center.
    # For EU, use: https://otlp.api.eu.newrelic.com:4317/v1/metrics
    endpoint = "https://otlp.nr-data.net:4317/v1/metrics"
    headers = {"api-key": NEW_RELIC_KEY}

    # Configure the OTLP exporter to send data to New Relic
    exporter = OTLPMetricExporter(endpoint=endpoint, headers=headers)

    # The reader periodically collects and exports metrics.
    # The default export interval is 60 seconds.
    reader = PeriodicExportingMetricReader(exporter)

    # The MeterProvider is the entry point of the SDK.
    provider = MeterProvider(metric_readers=[reader])

    # Set the global MeterProvider
    metrics.set_meter_provider(provider)

    # Returns a 'Meter' which is used to create metric instruments.
    return metrics.get_meter("pyairtouch.monitor")


def msg(log_msg: str) -> None:
    """Prints a message to the standard error stream for operational feedback."""
    print(log_msg, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments."""
    p = argparse.ArgumentParser(
        description="Monitors AirTouch devices and sends telemetry to New Relic."
    )
    p.add_argument(
        "--host", dest="airtouch_host", help="Connect by host name or IP address.", type=str
    )
    p.add_argument(
        "--debug", help="Enable debug logging.", action="store_true", default=False
    )
    return p.parse_args()


def _airtouch_id(airtouch: pyairtouch.AirTouch) -> str:
    """Returns a string identifier for an AirTouch system."""
    return f"{airtouch.name} ({airtouch.host})"


async def _monitor_airtouch(airtouch: pyairtouch.AirTouch, meter: metrics.Meter) -> None:
    """Initialises, monitors, and sends AirTouch data to New Relic."""
    success = await airtouch.init()
    if not success:
        msg(f"Error: {_airtouch_id(airtouch)} initialisation failed.")
        return

    msg(f"Continuously monitoring '{_airtouch_id(airtouch)}'...")

    # --- Create a SINGLE Metric Instrument ---
    # We will only create one gauge for the primary value: temperature.
    temp_gauge = meter.create_gauge(
        "airtouch.zone.temperature",
        unit="C",
        description="Current zone temperature. Other zone states are included as attributes.",
    )

    async def _on_ac_status_updated(ac_id: int) -> None:
        """Callback for AC status changes. Records metrics for each zone."""
        aircon = airtouch.air_conditioners[ac_id]
        logging.info(f"Telemetry update received for AC {ac_id} ({aircon.name}).")

        for zone in aircon.zones:
            # Only proceed if the zone has a temperature sensor and a valid reading
            if zone.current_temperature is None:
                logging.info(f"Skipping metric for Zone '{getattr(zone, 'name', zone.zone_id)}' due to no temperature reading.")
                continue

            # The primary value for our single metric is the temperature
            metric_value = zone.current_temperature

            # Start with the standard identifying attributes.
            attributes = {
                "airtouch.ac.id": aircon.ac_id,
                "airtouch.ac.name": getattr(aircon, "name", f"AC-{aircon.ac_id}"),
                "airtouch.zone.id": zone.zone_id,
                "airtouch.zone.name": getattr(zone, "name", f"Zone-{zone.zone_id}"),
                "airtouch.host": airtouch.host,
            }

            # Add all other Zone data points as additional attributes.
            attributes["airtouch.zone.powerState"] = 1 if zone.power_state == ZonePowerState.ON else 0
            attributes["airtouch.zone.controlMethod"] = zone.control_method.name
            attributes["airtouch.zone.spill"] = 1 if zone.spill_active else 0
            attributes["airtouch.zone.lowBattery"] = 1 if getattr(zone, 'low_battery', False) else 0
            if zone.target_temperature is not None:
                attributes["airtouch.zone.setPoint"] = zone.target_temperature
            if zone.current_damper_percentage is not None:
                attributes["airtouch.zone.openPercentage"] = zone.current_damper_percentage

            # Add all Air Conditioner data points as additional attributes.
            attributes["airtouch.aircon.powerState"] = aircon.power_state.name
            attributes["airtouch.aircon.activeMode"] = aircon.active_mode.name
            attributes["airtouch.aircon.activeFanSpeed"] = aircon.active_fan_speed.name
            if aircon.current_temperature is not None:
                attributes["airtouch.aircon.currentTemperature"] = aircon.current_temperature
            if aircon.target_temperature is not None:
                attributes["airtouch.aircon.targetTemperature"] = aircon.target_temperature

            # Set the single gauge with the temperature as the value
            # and all other data points as attributes.
            temp_gauge.set(metric_value, attributes)
            
            logging.info(f"Updated metric 'airtouch.zone.temperature' for Zone '{attributes['airtouch.zone.name']}'")


    for aircon in airtouch.air_conditioners:
        aircon.subscribe(_on_ac_status_updated)
        await _on_ac_status_updated(aircon.ac_id)

    await asyncio.Event().wait()


async def main(args: argparse.Namespace) -> None:
    """Main function to discover and monitor AirTouch systems."""
    # This will raise an error and stop if the key is missing.
    meter = setup_opentelemetry()

    if args.airtouch_host:
        msg(f"Attempting to connect to AirTouch at {args.airtouch_host}...")
    else:
        msg("Searching for AirTouch systems on the local network...")

    discovered_airtouches = await pyairtouch.discover(args.airtouch_host)
    if not discovered_airtouches:
        msg("No AirTouch systems were discovered.")
        return

    msg(f"Discovered {len(discovered_airtouches)} AirTouch system(s):")
    for airtouch in discovered_airtouches:
        msg(f"  - {_airtouch_id(airtouch)}")

    async with asyncio.TaskGroup() as tg:
        for airtouch in discovered_airtouches:
            tg.create_task(_monitor_airtouch(airtouch, meter))


if __name__ == "__main__":
    cli_args = parse_args()

    log_level = logging.DEBUG if cli_args.debug else logging.INFO
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    root_logger = logging.getLogger()
    if not root_logger.hasHandlers():
        root_logger.setLevel(log_level)
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(log_formatter)
        root_logger.addHandler(stream_handler)
        logging.getLogger("pyairtouch.discover").setLevel(
            logging.DEBUG if cli_args.debug else logging.WARNING
        )

    try:
        asyncio.run(main(cli_args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        msg("\nMonitoring stopped by user.")
    except Exception:
        logging.exception("An unexpected error occurred and the program has to stop.")