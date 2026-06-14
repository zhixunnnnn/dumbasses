import {
  NavigationProvider,
  useNavigation,
} from "./navigation/NavigationContext";
import AppShell from "./components/layout/AppShell";
import DashboardPage from "./components/dashboard/DashboardPage";
import ChatPage from "./components/chat/ChatPage";
import CompanyPage from "./components/company/CompanyPage";
import SettingsPage from "./components/settings/SettingsPage";
import ExplorePage from "./components/explore/ExplorePage";
import WatchlistsPage from "./components/watchlist/WatchlistsPage";
import EvidenceDashboard from "./evidence/components/dashboard/DashboardPage";
import EvidenceNews from "./evidence/components/news/NewsPage";
import EvidenceCompany from "./evidence/components/company/CompanyPage";
import FloatingChat from "./components/chat/FloatingChat";
import { ChatProvider } from "./components/chat/useChat";
import { AssistantPageContextProvider } from "./components/chat/PageContext";
import { ThemeProvider } from "./theme/ThemeContext";
import { WatchlistProvider } from "./components/watchlist/WatchlistContext";

function Routed() {
  const { route } = useNavigation();
  return (
    <>
      <AppShell>
        {route.name === "dashboard" && <DashboardPage />}
        {route.name === "assistant" && <ChatPage />}
        {route.name === "explore" && <ExplorePage />}
        {route.name === "watchlists" && <WatchlistsPage />}
        {route.name === "settings" && <SettingsPage />}
        {route.name === "company" && <CompanyPage id={route.id} />}
        {route.name === "evidence" && <EvidenceDashboard />}
        {route.name === "news" && <EvidenceNews />}
        {route.name === "evidenceCompany" && (
          <EvidenceCompany id={route.id} />
        )}
      </AppShell>
      {route.name !== "assistant" && <FloatingChat />}
    </>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <NavigationProvider>
        <WatchlistProvider>
          <AssistantPageContextProvider>
            <ChatProvider>
              <Routed />
            </ChatProvider>
          </AssistantPageContextProvider>
        </WatchlistProvider>
      </NavigationProvider>
    </ThemeProvider>
  );
}
