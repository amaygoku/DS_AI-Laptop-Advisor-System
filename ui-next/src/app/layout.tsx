import "./global.css";

export const metadata = {
  title: "Laptop Advisor Chat",
  description: "Chat UI for FastAPI + Ollama laptop advisor"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
