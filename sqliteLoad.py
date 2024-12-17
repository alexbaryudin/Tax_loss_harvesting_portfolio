import sqlite3
import pandas as pd

# Step 1: Define your CSV file path and SQLite database name
csv_file = "data.csv"  # Replace with your CSV file path
sqlite_db = "stocksDB.db"  # Name of the SQLite database

# Step 2: Load the CSV file into a Pandas DataFrame
df = pd.read_csv(csv_file)

# Step 3: Connect to SQLite database (or create one if it doesn't exist)
conn = sqlite3.connect(sqlite_db)

# Step 4: Write the DataFrame to the database
table_name = "stocks"  # Define the table name
df.to_sql(table_name, conn, if_exists="replace", index=False)

# Step 5: Verify data insertion
query = f"SELECT * FROM {table_name} LIMIT 15"
result = pd.read_sql_query(query, conn)
print(result)

# Close the connection
conn.close()
