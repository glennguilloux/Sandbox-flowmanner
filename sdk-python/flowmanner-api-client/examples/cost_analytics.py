"""View usage and cost analytics."""

from flowmanner_api_client import FlowmannerClient

def main():
    with FlowmannerClient(base_url="https://flowmanner.com") as fm:
        # Usage summary
        summary = fm.get_usage_summary(period="30d")
        print(f"Total tokens: {summary.get('total_tokens', 0):,}")
        print(f"Total cost: ${summary.get('total_cost', 0):.4f}")

        # Cost analytics
        costs = fm.get_cost_analytics(period="month")
        print(f"\nCost by model:")
        for model in costs.get("by_model", []):
            print(f"  {model.get('model')}: ${model.get('cost', 0):.4f}")

if __name__ == "__main__":
    main()
