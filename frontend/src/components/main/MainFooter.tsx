// frontend/src/components/main/FooterBar.tsx
export default function FooterBar() {
  if (!__APP_VERSION__) return null;

  const tooltip = [__APP_GIT_SHA__, __APP_BUILD_TIME__].filter(Boolean).join(' • ');

  return (
    <div className="p-2 text-right border-t bg-white text-sm text-gray-600">
      <span title={tooltip || undefined} aria-label={tooltip || undefined} className="cursor-default">
        v{__APP_VERSION__}
      </span>
    </div>
  );
}
