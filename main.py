from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from ebay import get_market_data
from pricing import analyze_market

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def home():
    return render_page()


@app.post("/", response_class=HTMLResponse)
def analyze(
    query: str = Form(...),
    condition: str = Form("A"),
    profit_margin: float = Form(40.0),
):
    sold_prices, active_prices, sold_items = get_market_data(query)

    if not sold_prices:
        return render_page(error="No comps found.")

    profit_decimal = float(profit_margin) / 100

    analysis = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit_decimal
    )

    return render_page(
        query=query,
        analysis=analysis,
        items=sold_items,
        comp_count=len(sold_prices)
    )


def render_page(query="", analysis=None, items=None, comp_count=0, error=None):

    images_html = ""

    if items:
        for item in items:
            images_html += f"""
            <div class="card" title="{item.get('title')}">
                <a href="{item.get('link')}" target="_blank">
                    {
                        f'<img src="{item.get("image")}" />'
                        if item.get("image")
                        else '<div class="placeholder"></div>'
                    }
                </a>
                <div class="price">${item.get('price')}</div>
            </div>
            """

    result_block = ""

    if analysis:
        result_block = f"""
        <div class="result-box">
            <div><strong>Comps:</strong> {comp_count}</div>
            <div><strong>Median:</strong> ${analysis['sold_median']}</div>
            <div><strong>Buy Below:</strong> ${analysis['max_buy']}</div>
            <div><strong>Target Sell:</strong> ${analysis['sell_target']}</div>
            <div><strong>Fast Sale:</strong> ${analysis['undercut']}</div>
            <div><strong>Volatility:</strong> {analysis['volatility']*100:.1f}%</div>
            <div><strong>Confidence:</strong> {analysis['confidence']}%</div>
            <div class="pressure">{analysis['pressure']}</div>
        </div>
        """

    error_block = f"<div class='error'>{error}</div>" if error else ""

    return f"""
    <html>
    <head>
        <title>CLAMS Resale Engine</title>
        <style>
            body {{
                background:#0d0d0d;
                color:white;
                font-family:Arial;
                text-align:center;
                padding:40px;
            }}

            h1 {{
                color:#00ffcc;
                font-size:40px;
            }}

            .result-box {{
                background:#1a1a1a;
                padding:20px;
                border-radius:15px;
                margin:30px auto;
                width:520px;
                font-size:16px;
                line-height:1.8;
            }}

            .pressure {{
                margin-top:10px;
                font-weight:bold;
                color:#00ffcc;
            }}

            .grid {{
                max-height:500px;
                overflow-y:auto;
                margin-top:30px;
            }}

            .card {{
                width:170px;
                background:#1a1a1a;
                display:inline-block;
                margin:8px;
                border-radius:12px;
                overflow:hidden;
                transition:0.2s;
            }}

            .card:hover {{
                transform:scale(1.05);
            }}

            .card img {{
                width:100%;
                height:170px;
                object-fit:cover;
            }}

            .placeholder {{
                height:170px;
                background:#222;
            }}

            .price {{
                padding:6px;
                font-weight:bold;
            }}

            input, select {{
                padding:10px;
                border-radius:8px;
                border:none;
                margin:5px;
            }}

            button {{
                padding:10px 20px;
                border-radius:8px;
                border:none;
                background:#00cc66;
                color:black;
                font-weight:bold;
            }}

            .error {{
                color:red;
                margin:20px;
            }}
        </style>
    </head>

    <body>

        <h1>CLAMS Resale Engine</h1>

        <form method="post">
            <input name="query" value="{query}" placeholder="Search item..." required>
            <select name="condition">
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
                <option value="Parts">Parts</option>
            </select>
            <input name="profit_margin" type="number" value="40">
            <button type="submit">Analyze</button>
        </form>

        {error_block}
        {result_block}

        <div class="grid">
            {images_html}
        </div>

    </body>
    </html>
    """
