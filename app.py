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

    # --- Highly Robust Rule-based Insights ---
    min_balance = forecast_df['ForecastedCashBalance'].min()
    max_balance = forecast_df['ForecastedCashBalance'].max()
    start_date = forecast_df['Date'].min().strftime('%Y-%m-%d')
    end_date = forecast_df['Date'].max().strftime('%Y-%m-%d')
    start_balance = forecast_df['ForecastedCashBalance'].iloc[0]
    end_balance = forecast_df['ForecastedCashBalance'].iloc[-1]
    avg_change = (end_balance - start_balance) / 90
    burn_rate = abs(avg_change)

    weekly_trends = forecast_df.set_index('Date').resample('W').mean().diff().mean().iloc[0]

    insights = ["Advanced Cashflow Analysis:", f"Forecast range: {start_date} to {end_date}"]

    if min_balance < 0:
        critical_dates = forecast_df[forecast_df['ForecastedCashBalance'] < 0]['Date']
        first_dip_date = critical_dates.iloc[0].strftime('%Y-%m-%d')
        insights.append(f"🚨 Critical Alert: Cash is expected to drop below zero on {first_dip_date}. Immediate financial action required.")
    elif min_balance < 5000:
        insights.append("⚠️ Caution: Projected minimum cash balance is under $5,000, indicating potential liquidity stress.")
    else:
        insights.append("✅ Excellent: Adequate cash levels projected across the forecast period.")

    insights.append(f"📉 Lowest projected cash balance: ${min_balance:.2f}")
    insights.append(f"📈 Highest projected cash balance: ${max_balance:.2f}")

    if weekly_trends < -50:
        insights.append("⚠️ Negative weekly trend detected. Evaluate expense reduction opportunities or revenue acceleration strategies.")
    elif weekly_trends > 50:
        insights.append("📊 Positive weekly cashflow trend observed. Evaluate strategic investment or savings opportunities.")
    else:
        insights.append("➖ Cashflow is steady week-over-week, indicating stability.")

    insights.append(f"🔥 Estimated daily cash burn rate: ${burn_rate:.2f}")

    if end_balance - start_balance > 5000:
        insights.append("💡 Significant cash surplus projected. Explore opportunities for investment, debt repayment, or expansion.")
    elif end_balance - start_balance < -5000:
        insights.append("🔻 Significant cash depletion projected. Immediate review of cash management strategies recommended.")

    insights.append("🔍 Continual weekly cashflow review is strongly advised to proactively manage financial health.")

    return "\n".join(insights)

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
