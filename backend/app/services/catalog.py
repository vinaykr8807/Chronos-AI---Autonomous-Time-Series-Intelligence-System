from app.core.schemas import DatasetResult


CATALOG: list[DatasetResult] = [
    DatasetResult(
        id="energy-001",
        title="California Energy Consumption",
        description="Hourly energy consumption data for California grid covering residential, commercial, and industrial sectors.",
        domain="energy",
        tags=["energy", "consumption", "california", "grid", "hourly"],
        relevanceScore=0.95,
        isTimeSeriesValidated=True,
        rowCount=52584,
        columnCount=12,
        timeRange={"start": "2018-01-01", "end": "2024-12-31"},
        missingPercent=2.3,
        source="local-storage",
        ref="datasetengineer/southern-california-energy-consumption",
        validationSummary="Backed by the cached Kaggle CSV in storage/datasets; EDA and training load the real dataframe.",
    ),
    DatasetResult(
        id="traffic-001",
        title="Highway Traffic Flow Analysis",
        description="Traffic sensor data with vehicle counts, average speed, and occupancy rates at regular time intervals.",
        domain="traffic",
        tags=["traffic", "highway", "vehicles", "speed", "flow"],
        relevanceScore=0.92,
        isTimeSeriesValidated=True,
        rowCount=234890,
        columnCount=15,
        timeRange={"start": "2019-06-01", "end": "2024-05-31"},
        missingPercent=1.2,
        source="local-seed",
    ),
    DatasetResult(
        id="sales-001",
        title="E-commerce Transaction Records",
        description="Retail transaction time series with product categories, customer segments, and revenue metrics.",
        domain="sales",
        tags=["e-commerce", "transactions", "revenue", "retail"],
        relevanceScore=0.91,
        isTimeSeriesValidated=True,
        rowCount=1247890,
        columnCount=24,
        timeRange={"start": "2020-01-01", "end": "2024-03-31"},
        missingPercent=0.8,
        source="local-seed",
    ),
    DatasetResult(
        id="finance-001",
        title="Stock Market Microstructure",
        description="High-frequency financial time series with trades, bid-ask spreads, and volume features.",
        domain="finance",
        tags=["stocks", "trading", "high-frequency", "order-book"],
        relevanceScore=0.89,
        isTimeSeriesValidated=True,
        rowCount=8945621,
        columnCount=32,
        timeRange={"start": "2023-01-01", "end": "2024-05-01"},
        missingPercent=0.1,
        source="local-seed",
    ),
    DatasetResult(
        id="iot-001",
        title="Industrial IoT Sensor Network",
        description="Manufacturing sensor readings for temperature, pressure, vibration, and machine health.",
        domain="iot",
        tags=["iot", "sensors", "manufacturing", "industrial", "health"],
        relevanceScore=0.94,
        isTimeSeriesValidated=True,
        rowCount=3456789,
        columnCount=45,
        timeRange={"start": "2021-03-01", "end": "2024-05-20"},
        missingPercent=1.5,
        source="local-seed",
    ),
]


def get_dataset(dataset_id: str) -> DatasetResult:
    for dataset in CATALOG:
        if dataset.id == dataset_id:
            return dataset
    return CATALOG[0].model_copy(update={"id": dataset_id, "title": f"Dataset {dataset_id}"})
