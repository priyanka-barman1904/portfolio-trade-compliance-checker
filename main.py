
import csv
import json
from decimal import Decimal, InvalidOperation


def to_decimal(value):
    """Convert a value to Decimal safely."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def get_holding_quantity(holdings, security_id):
    """Get total existing quantity of a particular security."""
    return sum(
        (
            to_decimal(holding["quantity"]) or Decimal("0")
            for holding in holdings
            if holding["security_id"] == security_id
        ),
        Decimal("0")
    )


def calculate_other_holdings_value(holdings, security_id):
    """
    Calculate the market value of all holdings
    except the security being purchased.
    """
    total = Decimal("0")

    for holding in holdings:
        if holding["security_id"] != security_id:
            quantity = to_decimal(holding["quantity"])
            market_price = to_decimal(holding["market_price"])

            if quantity is None or market_price is None:
                raise ValueError("Invalid portfolio holding data.")

            total += quantity * market_price

    return total


def check_trade(trade, portfolios):
    """
    Validate one proposed trade.
    Rules are executed strictly in the specified order.
    """

    portfolio_id = trade.get("portfolio_id")
    security_id = trade.get("security_id")
    action = trade.get("action")

    quantity = to_decimal(trade.get("quantity"))
    price = to_decimal(trade.get("price"))

    # Find portfolio reference data
    portfolio = portfolios.get(portfolio_id)

    if portfolio is None:
        return {
            "decision": "Rejected",
            "reason": "Portfolio not found."
        }

    holdings = portfolio["current_holdings"]

    # STEP 1: Validate trade data
    if (
        quantity is None
        or price is None
        or quantity <= 0
        or price <= 0
        or action not in ("Buy", "Sell")
    ):
        return {
            "decision": "Rejected",
            "reason": "Invalid trade data."
        }

    # STEP 2: Restricted security check
    if security_id in portfolio["restricted_securities"]:
        return {
            "decision": "Rejected",
            "reason": "Security is restricted for this portfolio."
        }

    cash_balance = to_decimal(portfolio["cash_balance"])

    if cash_balance is None or cash_balance < 0:
        return {
            "decision": "Rejected",
            "reason": "Invalid portfolio cash balance."
        }

    # STEP 3: Sell check
    if action == "Sell":

        existing_quantity = get_holding_quantity(
            holdings, security_id
        )

        if existing_quantity < quantity:
            return {
                "decision": "Rejected",
                "reason": "Insufficient holdings to sell."
            }

    # STEP 4: Buy affordability check
    if action == "Buy":

        trade_cost = quantity * price

        if trade_cost > cash_balance:
            return {
                "decision": "Rejected",
                "reason": "Insufficient cash for this buy order."
            }

        # STEP 5: Position concentration check

        # 1. Cash remaining after the trade
        post_trade_cash = cash_balance - trade_cost

        # 2. Existing quantity + proposed quantity
        existing_quantity = get_holding_quantity(
            holdings, security_id
        )

        post_trade_quantity = existing_quantity + quantity

        # 3. Value of the purchased security at trade price
        post_trade_security_value = post_trade_quantity * price

        # 4. Value of all OTHER holdings using their own market prices
        other_holdings_value = calculate_other_holdings_value(
            holdings, security_id
        )

        # 5. Total portfolio value after the trade
        total_portfolio_value_after = (
            post_trade_cash
            + post_trade_security_value
            + other_holdings_value
        )

        # 6. Calculate position concentration
        if total_portfolio_value_after <= 0:
            return {
                "decision": "Rejected",
                "reason": "Invalid total portfolio value."
            }

        position_pct = (
            post_trade_security_value
            / total_portfolio_value_after
        )

        max_position_pct = to_decimal(
            portfolio["max_position_pct"]
        )

        if max_position_pct is None:
            return {
                "decision": "Rejected",
                "reason": "Invalid maximum position limit."
            }

        # Strictly exceeds the maximum limit
        if position_pct > max_position_pct:
            return {
                "decision": "Needs Manual Sign-off",
                "reason": (
                    "Exceeds maximum position concentration "
                    "— requires approval."
                )
            }

    # STEP 6: All checks passed
    return {
        "decision": "Approved",
        "reason": "All compliance and execution checks passed."
    }


def load_portfolios(filename):
    """Load portfolio reference data from JSON."""
    with open(filename, "r", encoding="utf-8") as file:
        return json.load(file)



def process_trades(trades_file, portfolios_file, output_file):

    portfolios = load_portfolios(portfolios_file)

    results = []

    with open(
        trades_file,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file, skipinitialspace=True)

        if not reader.fieldnames:
            print("ERROR: CSV file is empty.")
            return

        # Clean CSV headers
        reader.fieldnames = [
            name.strip().lower() for name in reader.fieldnames
        ]

        required_columns = [
            "portfolio_id",
            "security_id",
            "action",
            "quantity",
            "price",
            "security_type"
        ]

        if not all(col in reader.fieldnames for col in required_columns):
            print("ERROR: Invalid CSV headers:", reader.fieldnames)
            return

        for trade in reader:

            # Clean trade values
            trade = {
                key.strip().lower(): value.strip()
                if value else ""
                for key, value in trade.items()
                if key is not None
            }

            if not any(trade.values()):
                continue

            # Get decision and reason
            decision_result = check_trade(trade, portfolios)

            # IMPORTANT: Keep trade details with decision
            output_row = {
                **trade,
                "decision": decision_result["decision"],
                "reason": decision_result["reason"]
            }

            results.append(output_row)

    # Output columns
    fieldnames = [
        "portfolio_id",
        "security_id",
        "action",
        "quantity",
        "price",
        "security_type",
        "decision",
        "reason"
    ]

    # Write output CSV
    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Display results
    print("\n========== TRADE COMPLIANCE RESULTS ==========\n")

    for index, result in enumerate(results, start=1):

        print(f"Trade {index}: {result['security_id']}")
        print(f"Portfolio: {result['portfolio_id']}")
        print(f"Action: {result['action']}")
        print(f"Decision: {result['decision']}")
        print(f"Reason: {result['reason']}")
        print("------------------------------------------")

    print("\nTotal trades processed:", len(results))
    print("Output saved successfully to:", output_file)


    # Write results to output CSV
    fieldnames = list(results[0].keys()) if results else [
        "portfolio_id",
        "security_id",
        "action",
        "quantity",
        "price",
        "security_type",
        "decision",
        "reason"
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(results)

    # Display results
    print("\n========== TRADE COMPLIANCE RESULTS ==========\n")

    for index, result in enumerate(results, start=1):

        print(f"Trade {index}: {result['security_id']}")
        print(f"Action   : {result['action']}")
        print(f"Decision : {result['decision']}")
        print(f"Reason   : {result['reason']}")
        print("----------------------------------------------")

    print(f"\nTotal trades processed: {len(results)}")
    print(f"Output saved to: {output_file}")


if __name__ == "__main__":

    process_trades(
        trades_file="trades.csv",
        portfolios_file="portfolios.json",
        output_file="output.csv"
    )
