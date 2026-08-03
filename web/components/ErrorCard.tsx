export default function ErrorCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="card error-card" role="alert">
      <strong>{title}</strong>
      <p className="muted">{message}</p>
    </div>
  );
}
