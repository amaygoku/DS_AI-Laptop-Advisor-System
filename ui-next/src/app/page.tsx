import Chat from "@/components/Chat";

export default function Page() {
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="logo">LA</div>
          <div>
            <div className="brandTitle">Laptop Advisor</div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="assistant">
            <div className="avatar">A</div>
            <div>
              <div className="assistantName">Advisor</div>
              <div className="assistantStatus">Sẵn sàng tư vấn</div>
            </div>
          </div>
        </header>

        <Chat />
      </main>
    </div>
  );
}
