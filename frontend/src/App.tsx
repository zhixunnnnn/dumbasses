import {
  NavigationProvider,
  useNavigation,
} from "./navigation/NavigationContext";
import AppShell from "./components/layout/AppShell";
import DashboardPage from "./components/dashboard/DashboardPage";
import ChatPage from "./components/chat/ChatPage";
import CompanyPage from "./components/company/CompanyPage";
import FloatingChat from "./components/chat/FloatingChat";

function Routed() {
  const { route } = useNavigation();
  return (
    <>
      <AppShell>
        {route.name === "dashboard" && <DashboardPage />}
        {route.name === "assistant" && <ChatPage />}
        {route.name === "company" && <CompanyPage id={route.id} />}
      </AppShell>
      {route.name !== "assistant" && <FloatingChat />}
    </>
  );
}

export default function App() {
  return (
    <NavigationProvider>
      <Routed />
    </NavigationProvider>
  );
}
