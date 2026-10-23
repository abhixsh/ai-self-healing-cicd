"""Small Flask app used as the target of the self-healing pipeline."""
from flask import Flask, jsonify, request

app = Flask(__name__)


def add(a: float, b: float) -> float:
    return a + b


@app.get("/")
def index():
    return jsonify(message="Hello from ai-self-healing-cicd")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/add")
def add_route():
    try:
        a = float(request.args.get("a", ""))
        b = float(request.args.get("b", ""))
    except ValueError:
        return jsonify(error="a and b must be numbers"), 400
    return jsonify(result=add(a, b))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
