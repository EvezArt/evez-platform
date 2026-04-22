# EVEZ Marketplace Templates

## Available Templates

### 1. LLM Fine-tuning Pipeline
```python
from evez import Task, step

@step
def prepare_data(data):
    return data.clean()

@step
def train_model(data):
    return fine_tune(data)

task = Task("fine_tuning", steps=[prepare_data, train_model])
```

### 2. Financial Signal Processor
```python
@step
def fetch_prices():
    return market_data()

@step
def analyze(data):
    return signals(data)

task = Task("finance", steps=[fetch_prices, analyze])
```

### 3. Data Cleaning Workflow
```python
@step
def extract(data):
    return raw_data()

@step
def transform(data):
    return cleaned(data)

task = Task("cleaning", steps=[extract, transform])
```
