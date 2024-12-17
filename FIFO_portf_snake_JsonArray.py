from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import sqlite3
from datetime import datetime
import pandas as pd
import yfinance as yf
import argparse
import uvicorn

# Initialize FastAPI application
app = FastAPI()

# Define the Pydantic model for JSON payload
class AccountRequest(BaseModel):
    account_id: str


# Function to fetch transactions from the database
def fetch_transactions(account_id: str, db_path="stocksDB.db"):
    """
    Fetch transactions for a given account ID from the database and clean the data.
    """
    conn = sqlite3.connect(db_path)  # Connect to SQLite database
    query = f"SELECT * FROM stocks WHERE `Account ID` = '{account_id}'"
    df = pd.read_sql_query(query, conn)  # Execute SQL query and load into a DataFrame
    conn.close()  # Close the database connection

    # Clean and convert the 'Stock Price' column to numeric
    if "Stock Price" in df.columns:
        df["Stock Price"] = df["Stock Price"].astype(str).str.replace(r"[^\d.]", "", regex=True)
        df["Stock Price"] = pd.to_numeric(df["Stock Price"], errors="coerce")

    # Ensure 'Number of Shares' is numeric
    df["Number of Shares"] = pd.to_numeric(df["Number of Shares"], errors="coerce")

    return df


# Function to fetch the current stock price
def get_current_stock_price(stock_name):
    """
    Fetch the current stock price using Yahoo Finance.
    """
    try:
        stock = yf.Ticker(stock_name)  # Initialize the Yahoo Finance Ticker
        current_price = stock.history(period="1d")['Close'].iloc[-1]  # Get the latest closing price
        return current_price
    except Exception as e:
        raise ValueError(f"Failed to fetch stock price for {stock_name}: {e}")


# Function to evaluate tax loss harvesting
def evaluate_tax_loss_harvesting(inventory, current_price):
    """
    Evaluate the potential gain/loss for tax loss harvesting and add exclusion flags.
    """
    results = []  # Store results for each batch
    total_loss_gain = 0  # Track the total gain/loss
    long_term_harvest_recommended = False  # Flag for tax loss harvesting recommendation

    for batch in inventory:
        price_per_unit = batch.get("price_per_unit")  # Price per unit for this batch
        purchase_date = datetime.strptime(batch["date_purchased"], "%m/%d/%y")  # Convert purchase date
        holding_period = (datetime.now() - purchase_date).days  # Calculate holding period in days
        potential_gain_loss = (current_price - float(price_per_unit)) * float(batch["quantity"])
        excluded_due_to_date = holding_period <= 365  # Exclusion based on short-term holding

        total_loss_gain += potential_gain_loss  # Accumulate the total gain/loss
        is_loss = potential_gain_loss < 0  # Check if this batch has a loss

        # Update recommendation flag if loss and eligible for harvesting
        if is_loss and not excluded_due_to_date:
            long_term_harvest_recommended = True

        # Append batch evaluation results
        results.append({
            "quantity": batch["quantity"],
            "price_per_unit": price_per_unit,
            "date_purchased": batch["date_purchased"],
            "potential_gain_loss": potential_gain_loss,
            "excluded_due_to_date": excluded_due_to_date
        })

    # Return the aggregated results
    return {
        "batch_results": results,
        "total_potential_gain_loss": total_loss_gain,
        "recommend_harvest": "yes" if long_term_harvest_recommended else "no"
    }


# Process account and generate the report
def process_account(account_id):
    """
    Process the account data to compute FIFO inventory and tax loss harvesting.
    """
    transactions_df = fetch_transactions(account_id)  # Fetch transactions from the database
    stocks_summary = []  # Store the final stock summary

    for stock_name in transactions_df["Stock Name"].unique():
        stock_transactions = transactions_df[transactions_df["Stock Name"] == stock_name]  # Filter by stock name
        inventory = []  # Track the inventory for FIFO calculations

        # Process FIFO transactions
        for _, tx in stock_transactions.iterrows():
            num_shares = float(tx["Number of Shares"])  # Number of shares in this transaction
            stock_price = float(tx["Stock Price"]) if not pd.isna(tx["Stock Price"]) else None  # Stock price

            # Handle buy transactions
            if num_shares > 0:
                if stock_price is None:
                    continue  # Skip transactions with missing stock price
                inventory.append({
                    "quantity": num_shares,
                    "price_per_unit": stock_price,
                    "date_purchased": tx["Date Purchased"]
                })
            # Handle sell transactions
            elif num_shares < 0:
                sell_quantity = abs(num_shares)
                while sell_quantity > 0:
                    if not inventory:
                        raise ValueError("Not enough stock to sell the requested quantity.")
                    batch = inventory[0]
                    if batch["quantity"] <= sell_quantity:
                        sell_quantity -= batch["quantity"]
                        inventory.pop(0)
                    else:
                        batch["quantity"] -= sell_quantity
                        sell_quantity = 0

        current_price = get_current_stock_price(stock_name)  # Get the current stock price
        evaluation = evaluate_tax_loss_harvesting(inventory, current_price)  # Evaluate tax loss harvesting

        # Compile stock summary for each batch
        for batch_result in evaluation["batch_results"]:
            stocks_summary.append({
                "account_id": account_id,
                "stock_ticker": stock_name,
                "number_of_shares_on_hand": batch_result["quantity"],
                "purchase_date": batch_result["date_purchased"],
                "purchase_price": batch_result["price_per_unit"],
                "current_stock_price": current_price,
                "potential_loss_gain": batch_result["potential_gain_loss"],
                "excluded_due_to_purchase_date": "yes" if batch_result["excluded_due_to_date"] else "no",
                "recommend_for_tax_loss_harvesting": evaluation["recommend_harvest"]
            })

    # Return the compiled summary as a DataFrame
    summary_df = pd.DataFrame(stocks_summary)
    return summary_df


# FastAPI POST route
@app.post("/process_account")
def process_account_endpoint(payload: AccountRequest):
    """
    FastAPI endpoint to process the account and return results.
    """
    try:
        account_id = payload.account_id  # Extract the account ID from the request
        if not account_id:
            raise HTTPException(status_code=400, detail="Account ID is required.")

        result_df = process_account(account_id)  # Process the account
        result_json = result_df.to_dict(orient="records")  # Remove the "summary" wrapper
        return JSONResponse(content=result_json)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# Main function
def main():
    """
    Entry point for the script to run in either API or interactive mode.
    """
    parser = argparse.ArgumentParser(description="Run the FIFO stock inventory calculator.")
    parser.add_argument("--mode", choices=["api", "interactive"], default="interactive",
                        help="Choose the mode: 'api' to run as a web server or 'interactive' to run interactively.")
    parser.add_argument("--account_id", type=str, help="Account ID for interactive mode.")
    args = parser.parse_args()

    if args.mode == "api":
        uvicorn.run(app, host="0.0.0.0", port=8000)  # Run the FastAPI app
    elif args.mode == "interactive":
        account_id = args.account_id or input("Enter the Account ID: ").strip()
        result_df = process_account(account_id)  # Process the account interactively
        print(result_df)  # Print the results


if __name__ == "__main__":
    main()
