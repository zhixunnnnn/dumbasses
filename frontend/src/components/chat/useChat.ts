import { useCallback, useRef, useState } from "react";
import { COMPANIES } from "../../data/companies";
import { buildSignalLeaders } from "../../data/signals";
import { QUADRANTS } from "../../lib/quadrant";
import { signedPercent } from "../../lib/format";

export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "I'm your ESG research copilot. Ask me about leaders, laggards, carbon intensity, a sector, or a specific ticker.",
};

function topByEsg() {
  return [...COMPANIES].sort((a, b) => b.esgScore - a.esgScore)[0];
}

function answer(prompt: string): string {
  const text = prompt.toLowerCase();

  const ticker = COMPANIES.find((c) =>
    text.includes(c.ticker.toLowerCase()),
  );
  if (ticker) {
    return `${ticker.name} (${ticker.ticker}) sits in the ${
      QUADRANTS[ticker.quadrant].title
    } quadrant with an ESG score of ${ticker.esgScore} (grade ${
      ticker.grade
    }) and a financial score of ${ticker.financialScore}. Momentum is ${signedPercent(
      ticker.momentum,
    )} with carbon intensity at ${ticker.esgMetrics.carbonIntensity} tCO₂e/$M.`;
  }

  if (text.includes("leader")) {
    const leaders = COMPANIES.filter((c) => c.quadrant === "leaders");
    const best = topByEsg();
    return `There are ${leaders.length} companies in the Leaders quadrant — high ESG and strong returns. ${best.name} tops the universe at ESG ${best.esgScore}. These names tend to pair low carbon intensity with above-median return on equity.`;
  }

  if (text.includes("laggard") || text.includes("risk")) {
    const laggards = COMPANIES.filter((c) => c.quadrant === "laggards");
    return `${laggards.length} companies fall into the Laggards quadrant — weak on both ESG and financial performance. These typically carry the highest controversy flags and elevated debt-to-equity ratios, so they screen out of most sustainable mandates.`;
  }

  if (text.includes("carbon") || text.includes("emission")) {
    const cleanest = [...COMPANIES].sort(
      (a, b) => a.esgMetrics.carbonIntensity - b.esgMetrics.carbonIntensity,
    )[0];
    return `${cleanest.name} runs the lowest carbon intensity in the universe at ${cleanest.esgMetrics.carbonIntensity} tCO₂e/$M, with ${cleanest.esgMetrics.renewableEnergyPct}% renewable energy. Across the book, emissions are trending lower as higher-ESG names compound their advantage.`;
  }

  if (text.includes("momentum") || text.includes("mover")) {
    const movers = buildSignalLeaders(COMPANIES, 3);
    const list = movers
      .map((m) => `${m.company.ticker} ${signedPercent(m.delta)}`)
      .join(", ");
    return `Top ESG momentum this quarter: ${list}. Momentum breadth is positive, meaning more than half the universe improved its composite score.`;
  }

  return "I can break down the matrix by quadrant, surface momentum leaders, compare carbon intensity, or profile any of the 300 companies. Try asking about 'leaders', 'carbon', or a specific ticker.";
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [pending, setPending] = useState(false);
  const counter = useRef(0);

  const nextId = () => {
    counter.current += 1;
    return `m${counter.current}`;
  };

  const send = useCallback((raw: string) => {
    const content = raw.trim();
    if (!content) return;
    const userMessage: ChatMessage = {
      id: nextId(),
      role: "user",
      content,
    };
    setMessages((prev) => [...prev, userMessage]);
    setPending(true);
    window.setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "assistant", content: answer(content) },
      ]);
      setPending(false);
    }, 480);
  }, []);

  return { messages, pending, send };
}

export const SUGGESTIONS = [
  "Who are the ESG leaders?",
  "Lowest carbon intensity?",
  "Top ESG momentum movers",
  "Profile the laggards",
];
