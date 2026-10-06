from typing import NotRequired
from langgraph.graph import MessagesState


class FlightState(MessagesState):
    country: NotRequired[str]
    start_location: NotRequired[str]
    end_location: NotRequired[str]
    departure_date: NotRequired[str]
    return_date: NotRequired[str]
    passengers: NotRequired[int]

    hours: NotRequired[float]
    price: NotRequired[float]

    selected_flight_id: NotRequired[str]
    booking_id: NotRequired[str]