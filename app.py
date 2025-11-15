# app.py
from flask import Flask, render_template, request
from datetime import datetime, timedelta
from events_providers import get_events_for_query

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """
    Main page: form + bulletin board with events.
    """
    # Default: no events until user searches.
    events = []
    lat, lng = None, None
    radius_km = 10.0  # default radius

    # Default date range: today → +7 days
    today = datetime.today().date()
    default_start = today.isoformat()
    default_end = (today + timedelta(days=7)).isoformat()

    # If query params provided, run search
    lat_param = request.args.get("lat")
    lng_param = request.args.get("lng")
    radius_param = request.args.get("radius")
    start_param = request.args.get("start_date")
    end_param = request.args.get("end_date")

    if lat_param and lng_param:
        try:
            lat = float(lat_param)
            lng = float(lng_param)
            radius_km = float(radius_param) if radius_param else radius_km

            start_str = start_param or default_start
            end_str = end_param or default_end
            start_dt = datetime.fromisoformat(start_str)
            end_dt = datetime.fromisoformat(end_str)

            events = get_events_for_query(lat, lng, radius_km, start_dt, end_dt)
        except Exception as e:
            print("Error parsing query params or fetching events:", e)

    return render_template(
        "index.html",
        events=events,
        lat=lat_param or "",
        lng=lng_param or "",
        radius=radius_param or str(radius_km),
        start_date=start_param or default_start,
        end_date=end_param or default_end
    )


if __name__ == "__main__":
    # For dev only; use a proper WSGI server in production
    app.run(debug=True)
