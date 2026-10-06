from langchain_core.tools import tool
from src.data import FLIGHT_INFORMATION
import math
@tool
def search_flights(
    start_location: str,
    end_location: str,
    departure_date : str,
) -> list:
    """
       Search for available flights from a start location to an end location.
    """
    results = []
    for flight in FLIGHT_INFORMATION:
        if (
            flight["start_location"].lower() == start_location.lower()
            and flight["end_location"].lower() == end_location.lower()
            and flight["departure_date"].lower() == departure_date.lower()
        ):
            results.append(flight)
    return results

@tool
def get_flight_detail_information(
    id : str
) -> None | dict:
    """
        Get detail information of a flight from flight's id. Return None if it doesn't exists
    """
    for flight in FLIGHT_INFORMATION:
        if flight["id"] == id:
            return flight
    return None

@tool
def list_flights(
    limit: int = 5, offset: int = 0
):
    """
    List available flights from the data storage with pagination.

    Args:
        limit: Maximum number of flights to return.
        offset: Number of flights to skip before returning results.
    """
    start = offset
    end = start + limit
    return FLIGHT_INFORMATION[start:end]

@tool
def summary_answer(flight : dict | None) -> str:
    """
    Generate a concise summary of the selected flight.
    Args:
        flight: Flight information to summarize. You can pass None if don't see any suitable
    """
    if flight is None:
        return "No flight is available or suitable with request"
    return f"""
        Flight {flight["id"]}: {flight["start_location"]} → {flight["end_location"]}.
        Departure: {flight["departure_date"]}, Return: {flight["return_date"]}.
        Duration: {flight["estimated_flight_hours"]} hours. Price: ${flight["price"]:.2f}.
    """

tools = [
    search_flights,
    get_flight_detail_information,
    list_flights,
    summary_answer
]
