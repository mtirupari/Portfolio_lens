"""Explicit invalidation prevents data and filter changes from retaining chat context."""
DEPENDENT = ['messages', 'chat_error', 'context_key', 'market', 'market_loaded_at', 'valuation', 'performance', 'pending_question']


def invalidate(state, clear_dataset=False):
    for key in DEPENDENT:
        state.pop(key, None)
    if clear_dataset:
        for key in ['data', 'normalized', 'issues', 'dataset_id', 'dataset_type', 'excluded_count', 'filters_tickers', 'filters_dates', 'ticker_scope', 'market_start', 'market_end', 'market_dates']:
            state.pop(key, None)


def activate(state, data, normalized, issues, dataset_type, dataset_id, excluded_count=0):
    invalidate(state, clear_dataset=True)
    state.update(data=data, normalized=normalized, issues=issues, dataset_type=dataset_type,
                 dataset_id=dataset_id, excluded_count=excluded_count)
