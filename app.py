from flask import Flask, request, jsonify, send_file, render_template
import pandas as pd
from datetime import datetime, timedelta
import os
from fpdf import FPDF
from PIL import Image
import pytesseract
import openai
import logging

UPLOAD_FOLDER = "uploads"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
    except FileExistsError:
        pass
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
openai.api_key = OPENAI_API_KEY
logging.basicConfig(filename='analytics.log', level=logging.INFO)

def forecast_cashflow(df):
    df['Date'] = pd.to_datetime(df['Date'])
    df['Amount'] = df['Amount'].astype(float)
    df['CashBalance'] = df['Amount'].cumsum()
    start_date = df['Date'].min()
    end_date = df['Date'].max()
    total_days = (end_date - start_date).days + 1
    avg_daily_cashflow = df['Amount'].sum() / total_days
    last_balance = df['CashBalance'].iloc[-1]
    forecast_dates = [end_date + timedelta(days=i) for i in range(1, 91)]
    forecast_balances = [last_balance + i * avg_daily_cashflow for i in range(1, 91)]
    return pd.DataFrame({'Date': forecast_dates, 'ForecastedCashBalance': forecast_balances})

def generate_insights_gpt(forecast_df):
    # GPT code temporarily disabled. Leaving here for future reactivation:
    # try:
    #     prompt = f"""
    #     You are a virtual CFO. Here is a 90-day cashflow forecast:
    #     {forecast_df.head(20).to_string(index=False)}
    #     Provide a plain-English summary of cash health and 2-3 actionable suggestions.
    #     """
    #     client = openai.OpenAI(api_key=OPENAI_API_KEY)
    #     response = client.chat.completions.create(
    #         model="gpt-3.5-turbo",
    #         messages=[
    #             {"role": "system", "content": "You are a financial analyst."},
    #             {"role": "user", "content": prompt}
    #         ]
    #     )
    #     return response.choices[0].message.content
    # except Exception as e:
    #     return f"AI Insights unavailable: {str(e)}"

    # --- Rule-based fallback summary ---
    min_balance = forecast_df['ForecastedCashBalance'].min()
    max_balance = forecast_df['ForecastedCashBalance'].max()
    insights = ["Rule-Based Forecast Summary:
"]
    if min_balance < 0:
        insights.append("⚠️ Your forecast shows a negative cash balance. Consider reducing expenses or boosting income.")
    else:
        insights.append("✅ Your forecast shows a positive cash position over the next 90 days.")
    if max_balance > 10000:
        insights.append("💡 Consider reinvesting or saving excess cash for growth opportunities.")
    insights.append("📊 Keep monitoring your forecast regularly.")
    return "
".join(insights)

def generate_pdf(insights, output_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "ForgeAI Flow - Cashflow Forecast", ln=True)
    pdf.set_font("Arial", '', 12)
    pdf.ln(10)
    for line in insights.split('\n'):
        pdf.multi_cell(0, 10, line)
    pdf.output(output_path)

def parse_text_to_table(text):
    lines = text.split('\n')
    data = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2:
            try:
                amount = float(parts[-1].replace(',', '').replace('$', ''))
                description = ' '.join(parts[:-1])
                data.append([datetime.today().date(), 'Expense' if amount < 0 else 'Income', description, amount])
            except:
                continue
    return pd.DataFrame(data, columns=['Date', 'Type', 'Description', 'Amount'])

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        elif filepath.endswith(('.png', '.jpg', '.jpeg')):
            img = Image.open(filepath)
            text = pytesseract.image_to_string(img)
            df = parse_text_to_table(text)
        else:
            return jsonify({"error": "Unsupported file type."}), 400

        forecast_df = forecast_cashflow(df)
        insights = generate_insights_gpt(forecast_df)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], "report.pdf")
        generate_pdf(insights, output_path)

        logging.info(f"Upload processed. File: {file.filename}")

        return send_file(output_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
