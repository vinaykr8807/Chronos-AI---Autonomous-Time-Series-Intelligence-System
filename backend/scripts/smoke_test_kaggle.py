import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
if os.getenv("KAGGLE_API_KEY") and not os.getenv("KAGGLE_KEY"):
    os.environ["KAGGLE_KEY"] = os.getenv("KAGGLE_API_KEY", "")

from app.core.schemas import SearchRequest
from app.services.discovery import DatasetDiscoveryService


def main() -> None:
    username = os.getenv("KAGGLE_USERNAME")
    token = os.getenv("KAGGLE_API_KEY")
    kaggle_key = os.getenv("KAGGLE_KEY")
    print(f"KAGGLE_USERNAME set: {bool(username)}")
    print(f"KAGGLE_API_KEY set: {bool(token)}")
    print(f"KAGGLE_KEY set: {bool(kaggle_key)}")

    service = DatasetDiscoveryService()
    response = service.search(SearchRequest(query="energy demand forecasting", domain="energy", limit=3))

    print(f"Discovery engine: {response.engine}")
    print(f"Result count: {len(response.results)}")
    for index, dataset in enumerate(response.results, start=1):
        print(f"{index}. [{dataset.source}] {dataset.title} score={dataset.relevanceScore} ref={dataset.ref}")

    if not response.results:
        raise SystemExit("No datasets returned.")

    if any(dataset.source == "kaggle" for dataset in response.results):
        print("Kaggle live search: OK")
    else:
        print("Kaggle live search: fallback catalog used")


if __name__ == "__main__":
    main()
