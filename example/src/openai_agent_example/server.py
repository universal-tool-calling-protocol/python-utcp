from fastapi import FastAPI, Body
from pydantic import BaseModel, Field
from typing import List, Literal

from utcp.shared.provider import HttpProvider
from utcp.shared.tool import utcp_tool
from utcp.shared.utcp_manual import UtcpManual

__version__ = "1.0.0"
BASE_PATH = "http://localhost:8080"

app = FastAPI(
    title="UTCP GymBro API",
    description="A mock API for logging workouts and getting exercise plans.",
    version=__version__,
)

# --- UTCP Manual Endpoint ---

@app.get("/utcp", response_model=UtcpManual, tags=["UTCP"])
def get_utcp_manual():
    """
    Provides the UTCP manual for discovering available tools.
    """
    return UtcpManual.create(version=__version__)

# --- Tool: Get Workout for Today ---

class TodaysWorkoutResponse(BaseModel):
    exercises: List[str] = Field(..., description="A list of exercises for today's workout.")
    focus: str = Field(..., description="The main muscle group or focus for today, e.g., 'Chest Day'.")

@utcp_tool(
    tool_provider=HttpProvider(
        name="get_workout_for_today",
        url=f"{BASE_PATH}/workout/today",
        http_method="GET"
    )
)
@app.get("/workout/today", response_model=TodaysWorkoutResponse, tags=["Workout"])
def get_workout_for_today() -> TodaysWorkoutResponse:
    """
    Gets the list of exercises for the current day's workout plan.
    """
    return {
        "exercises": ["Bench Press", "Incline Dumbbell Press", "Cable Flyes"],
        "focus": "Chest Day"
    }

# --- Tool: Log Exercise ---

class LogExerciseResponse(BaseModel):
    status: Literal["success"] = "success"
    message: str = Field(..., description="A confirmation message.")

@utcp_tool(
    tool_provider=HttpProvider(
        name="log_exercise",
        url=f"{BASE_PATH}/workout/log",
        http_method="POST"
    )
)
@app.post("/workout/log", response_model=LogExerciseResponse, tags=["Workout"])
def log_exercise(exercise_name: str, sets: int, reps: int, weight_kg: float) -> LogExerciseResponse:
    """
    Logs the details of a completed exercise session to the user's history.
    """
    print(f"Received exercise log: exercise_name={exercise_name}, sets={sets}, reps={reps}, weight_kg={weight_kg}")
    return {
        "status": "success",
        "message": f"Successfully logged {sets}x{reps} of {exercise_name} at {weight_kg}kg."
    } 