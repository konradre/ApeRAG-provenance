# Model Test Scripts

Tests the availability and functionality of models in the deployed ApeRAG system.

## Test Scripts

### test_embedding_model.py
Tests all available embedding models to verify which ones are actually usable.

### test_rerank_model.py
Tests all available rerank models to verify the reranking functionality.

### test_completion_model.py
Tests the specified completion model to verify text generation functionality. Provider, model, and prompts can be manually configured.

## Usage

```bash
# Test embedding models
python tests/model_test/test_embedding_model.py

# Test rerank models
python tests/model_test/test_rerank_model.py

# Test completion models (requires manual script configuration)
python tests/model_test/test_completion_model.py
```

## Environment Variables

| Variable | Default Value | Description |
|---|---|---|
| `APERAG_API_URL` | `http://localhost:8000` | ApeRAG API address |
| `APERAG_USERNAME` | `user@nextmail.com` | Login username |
| `APERAG_PASSWORD` | `123456` | Login password |

## Output

Each script will generate:
- Real-time console output
- Detailed test report in JSON format

## Dependencies

```bash
pip install httpx yaml
```