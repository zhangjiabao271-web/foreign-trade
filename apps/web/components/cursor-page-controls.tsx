"use client";

export function CursorPageControls({
  query,
  label,
  disabled = false,
}: {
  query: {
    hasNextPage: boolean;
    isError: boolean;
    isFetching: boolean;
    isFetchingNextPage: boolean;
    data?: unknown;
    fetchNextPage: () => Promise<unknown>;
    restart: () => Promise<unknown>;
  };
  label: string;
  disabled?: boolean;
}) {
  if (!query.hasNextPage && !query.isError) return null;
  return (
    <div className="list-message">
      {query.hasNextPage && (
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || query.isFetching}
          onClick={() => void query.fetchNextPage()}
        >
          {query.isFetchingNextPage ? `正在加载${label}…` : `加载更多${label}`}
        </button>
      )}
      {query.isError && (
        <>
          <p role="alert">
            {query.data
              ? `${label}分页加载失败，已读取的记录仍保留。可重试，或重新加载清单。`
              : `${label}清单加载失败，请重新加载清单。`}
          </p>
          <button
            type="button"
            className="quiet-button"
            disabled={disabled || query.isFetching}
            onClick={() => void query.restart()}
          >
            重新加载{label}清单
          </button>
        </>
      )}
    </div>
  );
}
