from flask import Blueprint, jsonify, render_template, request
from .services.query_service import get_dashboard_data, get_ticker_page_data
from .services.compare_service import compare_tickers
from .services.answer_service import answer_question
from .services.compare_answer_service import compare_answer

bp = Blueprint("main", __name__)

@bp.route("/")
def dashboard():
    data = get_dashboard_data()
    return render_template("dashboard.html", data=data)

@bp.route("/ticker/<ticker>")
def ticker_page(ticker):
    data = get_ticker_page_data(ticker)
    return render_template("ticker.html", data=data)

@bp.route("/compare")
def compare():
    ticker_a = request.args.get("ticker_a")
    ticker_b = request.args.get("ticker_b")
    data = compare_tickers(ticker_a, ticker_b)
    return render_template("compare.html", data=data)

@bp.route("/api/ask", methods=["POST"])
def ask():
    payload = request.get_json() or {}
    ticker = paylaod.get("ticker")
    question = payload.get("question")

    if not ticker or not question:
        return jsonify({"error": "ticker and question are required"}), 400
    result = answer_question(ticker.upper(), question)
    return jsonify(result)


@bp.route("/api/compare-ask", methods=["POST"])
def compare_ask():
    payload = request.get_json() or {}
    ticker_a = payload.get("ticker_a")
    ticker_b = payload.get("ticker_b")
    question = payload.get("question")

    if not ticker_a or not ticker_b or not question:
        return jsonify({"error": "ticker_a, ticker_b, and question are required"}), 400

    result = compare_answer(ticker_a.upper(), ticker_b.upper(), question)
    return jsonify(result)