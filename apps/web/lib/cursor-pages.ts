export function collectCursorItems<T extends { id: string }>(data: {
  pages: { items: T[] }[];
}) {
  const items = Array.from(
    new Map(
      data.pages.flatMap((page) => page.items).map((item) => [item.id, item]),
    ).values(),
  );
  return { items, count: items.length };
}
