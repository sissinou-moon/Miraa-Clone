# Request

A Python backend project for handling HTTP requests and processing data.

## 📖 Overview

`Request` is a Python-based backend service designed to handle HTTP request processing, data validation, and response generation. It provides a robust and scalable solution for building RESTful APIs and microservices.

## ✨ Features

- **HTTP Request Handling** – Process incoming requests with proper validation and routing.
- **Data Validation** – Built-in schema validation for request payloads.
- **Error Handling** – Structured error responses with appropriate HTTP status codes.
- **Middleware Support** – Easy-to-add middleware for logging, authentication, and rate limiting.
- **Async Support** – Asynchronous request handling for high-throughput scenarios.
- **Documentation** – Auto-generated API documentation using docstrings.
- **Testing** – Comprehensive test coverage with `pytest`.

## 🛠️ Installation

### Prerequisites

- Python ≥ 3.9
- pip ≥ 21.0

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/request.git
cd Request

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

## 📦 Project Structure

```
Request/
├── README.md
├── requirements.txt
├── setup.py
├── tests/
│   └── __init__.py
├── src/
│   ├── __init__.py
│   ├── app.py
│   └── handlers/
│       ├── __init__.py
│       ├── base.py
│       ├── auth.py
│       └── endpoints.py
├── docs/
│   └── api.md
└── scripts/
    └── run.py
```

## 🚀 Usage

### Starting the Server

```bash
python -m src.app
```

### Making Requests

```bash
# Example GET request
curl -X GET "http://localhost:8000/api/users"

# Example POST request
curl -X POST "http://localhost:8000/api/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

### Using the SDK (Python)

```python
from request import Client

client = Client("http://localhost:8000")

# Get a user
user = client.get("/api/users/1")

# Create a user
new_user = client.post("/api/users", json={
    "name": "Bob",
    "email": "bob@example.com"
})
```

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/users` | List all users |
| `GET`  | `/api/users/:id` | Get a single user |
| `POST` | `/api/users` | Create a new user |
| `PUT`  | `/api/users/:id` | Update a user |
| `DELETE` | `/api/users/:id` | Delete a user |
| `POST` | `/api/login` | Authenticate and get a token |

### Authentication

All protected endpoints require a valid `Authorization` header:

```bash
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/users"
```

## 🧪 Running Tests

```bash
pytest tests/ -v
```

Coverage report:

```bash
pytest --cov=src --cov-report=html
```

## 🐳 Docker

```bash
docker-compose up --build
```

## 🔧 Configuration

Create a `.env` file in the project root:

```env
HOST=0.0.0.0
PORT=8000
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///./app.db
```

## 📝 API Response Examples

### Success Response (200 OK)

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com"
  }
}
```

### Error Response (404 Not Found)

```json
{
  "status": "error",
  "code": "NOT_FOUND",
  "message": "User not found"
}
```

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 📜 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

## 👥 Authors

- **Yassine** – [yassine](https://github.com/yassine)

## 🙏 Acknowledgments

- Inspiration from FastAPI, Flask, and other modern Python web frameworks.
- Thanks to the open-source community!

---

> 💡 **Tip:** Check out the [API documentation](docs/api.md) for detailed endpoint specifications.
