export default function DebugPanel({ open, data }: { open: boolean; data: any }) {
  if (!open) return null;
  return (
    <div className="debugPanel">
      <div className="debugTitle">Debug</div>
      <pre className="debugPre">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
