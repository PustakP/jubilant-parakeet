from flask import Flask, request, jsonify
from gpt_researcher import GPTResearcher
from datetime import datetime, timedelta
import os
from flask_cors import CORS
from sqlalchemy import create_engine, Table, Column, Integer, String, Date, MetaData, select, func

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')  # This should be your PostgreSQL connection string

engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Define the quantum_reports table
quantum_reports = Table('quantum_reports', metadata,
    Column('id', Integer, primary_key=True),
    Column('created_at', Date, server_default=func.current_date()),
    Column('report_type', String),
    Column('time_frame', String),
    Column('start_date', Date),
    Column('end_date', Date),
    Column('report', String)
)

metadata.create_all(engine)  # This will create the table if it doesn't exist

app = Flask(__name__)
CORS(app)

@app.route('/')
async def index():
    return jsonify({"message": "# Welcome to the Quantum News API!"})

async def get_cached_report(report_type, time_frame, start_date, end_date):
    with engine.connect() as conn:
        select_stmt = select(quantum_reports.c.report, quantum_reports.c.start_date, quantum_reports.c.end_date).where(
            (quantum_reports.c.report_type == report_type) &
            (quantum_reports.c.time_frame == time_frame) &
            (quantum_reports.c.start_date == start_date) &
            (quantum_reports.c.end_date == end_date)
        ).order_by(quantum_reports.c.created_at.desc())
        result = conn.execute(select_stmt).first()
        if result:
            result_start_date = result.start_date
            result_end_date = result.end_date

            if (result_start_date == start_date and result_end_date == end_date):
                print(f"Cache hit for {report_type}, {time_frame}, {start_date}, {end_date}")
                return result.report
            else:
                print(f"Cache miss (old report) for {report_type}, {time_frame}, {start_date}, {end_date}")
        else:
            print(f"Cache miss (no report) for {report_type}, {time_frame}, {start_date}, {end_date}")
    return None


async def cache_report(report_type, time_frame, start_date, end_date, report):
    with engine.connect() as conn:
        insert_stmt = quantum_reports.insert().values(
            report_type=report_type,
            time_frame=time_frame,
            start_date=start_date,
            end_date=end_date,
            report=report
        )
        conn.execute(insert_stmt)
        conn.commit()
        print(f"Cached report for {report_type}, {time_frame}, {start_date}, {end_date}")

@app.route('/quantum_news_report', methods=['GET'])
async def get_quantum_news_report():
    report_type = request.args.get('report_type', 'research_report')
    time_frame = request.args.get('time_frame', 'day')
    
    if time_frame not in ['day', 'week', 'month']:
        return jsonify({"error": "Invalid time frame. Use 'day', 'week', or 'month'."}), 400
    
    end_date = datetime.now().date()
    if time_frame == 'day':
        start_date = end_date - timedelta(days=1)
    elif time_frame == 'week':
        start_date = end_date - timedelta(weeks=1)
    else:  # month
        start_date = end_date - timedelta(days=30)
    
    print(f"Requesting report for {report_type}, {time_frame}, {start_date}, {end_date}")
    
    try:
        # Try to get cached report
        print(f"Debug: report_type={report_type}, time_frame={time_frame}, start_date={start_date}, end_date={end_date}")
        cached_report = await get_cached_report(report_type, time_frame, start_date, end_date)
        
        if cached_report:
            print("Returning cached report")
            return jsonify({
                "time_frame": time_frame,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "report": cached_report,
                "source": "cache"
            })
        
        print("No cached report found, generating new report")
        # If no cached report, generate a new one
        query = f"Latest news and developments in quantum physics from {start_date} to {end_date}"
        researcher = GPTResearcher(query=query, report_type=report_type)
        await researcher.conduct_research()
        report = await researcher.write_report()
        
        # Cache the new report
        await cache_report(report_type, time_frame, start_date, end_date, report)
        
        return jsonify({
            "time_frame": time_frame,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "report": report,
            "source": "fresh"
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)