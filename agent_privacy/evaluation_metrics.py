"""Usage observations shared by the evaluation ledger and scorer."""

USAGE_FIELDS = ("input_tokens", "output_tokens", "cost_usd")
TRANSFER_FIELDS = ("outbound_bytes", "response_bytes", "latency_ms")


def trace_metrics(trace):
    attempts = [event for event in trace if event["event"] == "send_attempt"]
    results = [event for event in trace if event["event"] == "send_result"]
    missing_results = len(attempts) - len(results)
    responses = [event["response"] for event in results if event["response"] is not None]
    metrics = {
        "send_count": len(attempts),
        "outbound_bytes": sum(event["body"]["byte_length"] for event in attempts),
        "response_bytes": sum(response["byte_length"] for response in responses)
        if responses or not attempts else None,
        "response_bytes_unknown_results": len(attempts) - len(responses),
        "latency_ms": sum(event["latency_ms"] for event in results)
        if results or not attempts else None,
        "latency_ms_unknown_results": missing_results,
    }
    for field in USAGE_FIELDS:
        known = [event["usage"][field] for event in results if event["usage"][field] is not None]
        metrics[field] = sum(known) if known else None
        metrics[field + "_known_results"] = len(known)
        metrics[field + "_unknown_results"] = len(attempts) - len(known)
    return metrics
