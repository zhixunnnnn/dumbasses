from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent import AssistantResponse, ChatMessage


ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_CHAT_HISTORY_DB = ROOT / "backend" / "data" / "chat_history.sqlite3"
_RUNTIME_DATA_DIR = Path(
    os.environ.get("POLYFINTECH_DATA_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or _BUNDLED_CHAT_HISTORY_DB.parent
).expanduser()
DEFAULT_CHAT_HISTORY_DB = Path(
    os.environ.get("CHAT_HISTORY_DB_PATH")
    or (_RUNTIME_DATA_DIR / "chat_history.sqlite3")
).expanduser()

LEGACY_SHOWCASE_SESSION_IDS = (
    "session-8476fde81c0142aeb60fb86cdbab95f4",
    "session-8b8382a7147a45e69a893a320b9b3878",
    "session-768c3a0945b74d9d954657f8dc91b118",
    "session-766ebd0c5c514023ada3e3d95c59a5bb",
    "session-77b97f00f4c1447ea380ea5724de7748",
    "session-6ee9c3afadad487a84978b8a72e863d5",
    "session-46c66ce525144b41b0f0287619ac862c",
    "session-c8215663231240b6bf63bbd7836c272f",
    "session-4f885f9ba921404e89bef0e12108f219",
    "session-e295c3eafd7d4c94b9a79980394f99f1",
    "session-19f4821f248a4bdfa2b9ae8d456a24ef",
    "session-e7bf473f0704406f8d269d9fd8fb9940",
)

SHOWCASE_CHATS: tuple[dict[str, Any], ...] = (
    {
        "id": "session-showcase-report",
        "age_minutes": 5,
        "title": "Generate a Sembcorp ESG investment report",
        "prompt": (
            "Generate an investment-grade ESG report for Sembcorp Industries using "
            "the current dashboard evidence and latest scraped disclosures."
        ),
        "response": """## Sembcorp Industries ESG report

The report is ready. It combines the current evidence engine, the rating outlook, transition targets, regulatory coverage, and source-linked company disclosures.

### Executive view

- **ESG consensus:** 81.7 / 100
- **Evidence score:** 80.0 / 100 with 60.3% confidence
- **2026 rating outlook:** AA, likely hold
- **Transition signal:** renewables capacity reached 15 GW in 2025 against a 25 GW target for 2028
- **Watchpoint:** Sembcorp expects near-term emissions to rise following the Alinta Energy acquisition and has updated its emissions-intensity pathway

Open the report artifact below to preview it or download it as a PDF.""",
        "sources": [
            {
                "title": "Sembcorp Sustainability Report 2025",
                "url": "https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf",
                "snippet": "2025 performance, climate targets, and material ESG disclosures.",
                "source": "bright_data+pdf",
            },
            {
                "title": "Sembcorp Climate Action Plan",
                "url": "https://www.sembcorp.com/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/",
                "snippet": "Current renewable-capacity, emissions-intensity, and net-zero targets.",
                "source": "bright_data",
            },
        ],
        "tool_results": [
            {
                "name": "get_company_esg",
                "status": "ok",
                "summary": "Loaded Sembcorp's ratings, evidence pillars, forecast, and compliance signals.",
                "sourceCount": 1,
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped Sembcorp's 2025 sustainability disclosures and climate targets.",
                "sourceCount": 2,
            },
        ],
        "workflow_steps": [
            {
                "label": "Loaded ESG evidence",
                "status": "ok",
                "detail": "Collected the current rating, evidence, forecast, and compliance record.",
                "toolName": "get_company_esg",
            },
            {
                "label": "Scraped current disclosures",
                "status": "ok",
                "detail": "Extracted transition targets from Sembcorp's 2025 publications.",
                "toolName": "scrape_url",
            },
            {
                "label": "Generated report",
                "status": "ok",
                "detail": "Built a source-linked ESG investment report and PDF-ready artifact.",
                "toolName": "report_generation",
            },
        ],
        "report": {
            "title": "Sembcorp Industries ESG Investment Report",
            "generatedAt": "2026-09-05T00:00:00+08:00",
            "markdown": """# Sembcorp Industries ESG Investment Report

## Executive summary

Sembcorp Industries combines a strong current ESG consensus with high evidence coverage and a credible renewable-growth programme. The current rating outlook is AA and likely to hold. The central investment tension is between rapid renewable deployment and the near-term emissions effect of a larger thermal portfolio following the Alinta Energy acquisition.

## Current ESG position

| Measure | Current view |
|---|---:|
| ESG consensus | 81.7 / 100 |
| Evidence score | 80.0 / 100 |
| Evidence confidence | 60.3% |
| Environmental pillar | 80.0 / 100 |
| Social pillar | 100.0 / 100 |
| Governance pillar | 50.0 / 100 |
| 2026 rating outlook | AA, likely hold |

The evidence engine shows broad disclosure coverage, with water management remaining the principal uncovered material topic in the current record.

## Transition plan

Sembcorp reported 15 GW of gross installed renewable capacity at the end of 2025 and targets 25 GW by 2028. Its updated climate pathway targets emissions intensity of 0.26 tCO2e/MWh by 2035 and net-zero Scope 1 and 2 emissions by 2050.

The company also states that emissions are expected to increase in the near term following the Alinta Energy acquisition. This makes delivery against the revised intensity pathway a key monitoring point.

## Investment interpretation

**Strengths:** high peer-relative ESG consensus, strong environmental and social evidence, expanding renewable capacity, and source-linked transition targets.

**Risks:** governance evidence trails the other pillars, transition execution must absorb a larger thermal portfolio, and evidence confidence is not yet high enough to treat every disclosure as independently verified.

## Monitoring checklist

1. Progress from 15 GW toward the 25 GW renewable-capacity target.
2. Movement in group emissions intensity following the Alinta consolidation.
3. New evidence on water management and governance controls.
4. Any change to the AA rating baseline or evidence confidence.

## Sources

- [Sembcorp Sustainability Report 2025](https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf)
- [Sembcorp Climate Action Plan](https://www.sembcorp.com/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/)
""",
        },
    },
    {
        "id": "session-showcase-prediction",
        "age_minutes": 12,
        "title": "Sembcorp's likely ESG score from current news",
        "prompt": (
            "What is the current ESG score likely to be for Sembcorp, "
            "based on its current news?"
        ),
        # Captured verbatim from the deployed agent answering this exact prompt.
        # Do not hand-edit: re-run the prompt and paste the new reply instead, so the
        # showcase stays a real transcript rather than a written-up impression of one.
        "response": "**Sembcorp Industries' current ESG evidence score is 80 out of 100, and the news flow strongly supports this level.**\n\nThe app's computed ESG score of **80.0/100** (confidence 60.3%) is built from pillar scores of Environmental 80, Social 100, and Governance 50. The company sits in the **FUTURE_LEADERS** quadrant — high evidence score with positive momentum — and is not flagged as an underpriced improver (the market already prices in its trajectory).\n\n### How current news supports the score\n\nRecent news and validated evidence paint a consistently positive picture, with no material controversies detected:\n\n- **Renewable energy expansion**: Sembcorp completed the S$246 million acquisition of Indian solar company ReNew Sun Bright, secured solar/gas PPAs with Equinix in Singapore, received conditional approval for a renewable power import project from Malaysia, and announced a landmark A$6.5 billion acquisition of Alinta Energy in Australia.\n- **Emissions disclosure & targets**: The company publicly reports Scope 1, 2, and partial Scope 3 emissions under the GHG Protocol, with a target to halve emissions by 2030 (from a 2010 baseline) and reach net-zero by 2050. Total 2024 operational emissions were ~9.3 million tCO2e.\n- **No controversies**: Community sentiment adjustment is zero. No negative ESG incidents, regulatory actions, or social disputes appear in the evidence base.\n- **Governance pillar at 50** is the relative weak point — this reflects the app's assessment of board structure and disclosure practices, not any news-driven controversy.\n\n### MSCI rating context\n\nSembcorp's last disclosed MSCI rating was **AA** (2024). The app's experimental estimate for 2026 is a **likely hold at AA**, though this is a persistence baseline (insufficient panel history for a fitted model) and should be treated as a directional hypothesis only.\n\n### Summary\n\nThe 80/100 evidence score is well-grounded in the current news: aggressive renewables M&A, credible emissions targets, transparent disclosure, and zero controversy signal. The score could edge higher if governance disclosure improves or if the renewable portfolio shift accelerates emissions reductions beyond current \"Stable\" trend.",
        "sources": [
            {
                "title": "SGIPL%20AR%202024 25",
                "url": "https://www.sembcorpindia.com/public/admin/upload/annual-report/SGIPL%20AR%202024-25.pdf",
                "snippet": "Reshaping Energy Renewing Possibilities Annual Report 2024-25 Sembcorp Green Infra Private Limited (Formerly, Green Infra Wind Energy Private Limited and Green Infra Wind Energy Limited) Contents Corporate overview 04-59 Highlights of 2025 About Us Excellence in Corporate Social Responsibility Our Transformational Journey Board of Directors Financial Scoreca...",
                "source": "native_fetch_after_provider_error+pdf",
                "sourceClass": "non_verified"
            },
            {
                "title": "sembcorp ar25",
                "url": "https://www.sembcorp.com/media/z2ypqfjj/sembcorp-ar25.pdf",
                "snippet": "Sembcorp Industries Annual Report 2025 As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition towards a sustainable and low-carbon future. We believe in building businesses that deliver long-term shareholder value and growth. Overview Group FY2025 Highlights 1 Our Presence 2...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "Sembcorp AR2024 SinglePages",
                "url": "https://media.sembcorp.com/data/cms/ar/ar2024/assets/pdf/Sembcorp_AR2024_SinglePages.pdf",
                "snippet": "Sembcorp Industries Annual Report 2024 As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition towards a sustainable and low-carbon future. We believe in building businesses that deliver long-term shareholder value and growth. Overview Group FY2024 Highlights 1 Our Presence 2...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "sembcorp ar2023",
                "url": "https://www.sembcorp.com/media/vhzjfn5u/sembcorp_ar2023.pdf",
                "snippet": "Sembcorp Industries Annual Report 2023 Sembcorp is a leading renewables player in Asia. We are committed to transforming our portfolio from brown to green and driving energy transition, creating lasting value for our stakeholders. Driving Energy Transition Overview Group FY2023 Highlights 2 Growing Market Opportunities 4 Leveraging Strengths 6 Climate Roadma...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "Sembcorp Industries AR2025",
                "url": "https://ne-cdn.eurolandir.com/press-releases-attachments./4015966/Sembcorp-Industries_AR2025.pdf",
                "snippet": "Sembcorp Industries Annual Report 2025 As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition towards a sustainable and low-carbon future. We believe in building businesses that deliver long-term shareholder value and growth. Overview Group FY2025 Highlights 1 Our Presence 2...",
                "source": "bright_data+pdf",
                "sourceClass": "non_verified"
            },
            {
                "title": "Sembcorp Industries",
                "url": "https://links.sgx.com/1.0.0/corporate-announcements/E3OPH06R1G42R3UK/838159_Sembcorp_Annual%20Report_2024.pdf",
                "snippet": "Page 1. Sembcorp Industries. Annual Report 2024. Page 2. As a leading ... Environmental, Social and Governance Review. Consolidated.Read more",
                "source": "bright_data_serp",
                "sourceClass": "verified"
            },
            {
                "title": "sustainability report",
                "url": "https://www.sembcorp.com/media/nhlbsvgy/sustainability_report.pdf",
                "snippet": "Sustainability Report Our Sustainability Framework​ 20 Our Approach to Sustainability​ 21 • Reporting Framework​ • Materiality ​ • Reporting Scope • Assurance • Supporting the Sustainable Development Goals • Sustainability Governance • Sustainability-linked Performance Incentives • Memberships and Associations​ Our Environmental, Social and Governance Priori...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "System-Level and Structure-Based Approaches",
                "url": "https://bschool.nus.edu.sg/cgs/wp-content/uploads/sites/145/2026/03/Cases-in-Sustainability_System-Level-and-Structure-Based-Approaches_2026-Mar.pdf",
                "snippet": "sustainability through low-carbon growth (Sembcorp Industries, 2025). Page 49. 49. Decarbonisation Solutions. Sembcorp helps companies develop ...Read more",
                "source": "bright_data_serp",
                "sourceClass": "non_verified"
            },
            {
                "title": "Sembcorp",
                "url": "https://sembcorp.com/",
                "snippet": "Sembcorp Industries 1H2026 Results. August 07, 2026. Sembcorp Receives Conditional Approval for Renewable Power Import Project From Peninsular Malaysia to ...",
                "source": "bright_data",
                "sourceClass": "verified"
            },
            {
                "title": "Initial Report: Sembcorp Industries Ltd (U96.SI), 304% 5-yr Potential Upside (EIP, Girvin CHANG)",
                "url": "https://nextgeninvestors.substack.com/p/initial-report-sembcorp-industries",
                "snippet": "Initial Report: Sembcorp Industries Ltd (U96.SI), 304% 5-yr ... Its experience and capabilities in renewable energy, water management, and ...",
                "source": "bright_data",
                "sourceClass": "non_verified"
            }
        ],
        "tool_results": [
            {
                "name": "get_company_esg",
                "status": "ok",
                "summary": "Sembcorp Industries: ESG evidence 80.0; MSCI rating estimate 2026 — likely hold to AA (baseline: ratings persistence (insufficient history for a fitted model — 11 panel rows)).",
                "sourceCount": 0
            },
            {
                "name": "research_company_esg_news",
                "status": "ok",
                "summary": "Collected 8 company ESG/news references for: Sembcorp Industries",
                "sourceCount": 8
            },
            {
                "name": "get_validated_esg_evidence",
                "status": "ok",
                "summary": "Loaded 48 grouped claims and 24 sources for Sembcorp Industries.",
                "sourceCount": 24
            }
        ],
        "workflow_steps": [
            {
                "label": "Get Company Esg",
                "status": "ok",
                "detail": "Sembcorp Industries: ESG evidence 80.0; MSCI rating estimate 2026 — likely hold to AA (baseline: ratings persistence (insufficient history for a fitted model — 11 panel rows)).",
                "toolName": "get_company_esg"
            },
            {
                "label": "Collected company ESG news",
                "status": "ok",
                "detail": "Collected 8 company ESG/news references for: Sembcorp Industries",
                "toolName": "research_company_esg_news"
            },
            {
                "label": "Get Validated Esg Evidence",
                "status": "ok",
                "detail": "Loaded 48 grouped claims and 24 sources for Sembcorp Industries.",
                "toolName": "get_validated_esg_evidence"
            }
        ],
        "report": None,
    },
    {
        "id": "session-showcase-web-scrape",
        "age_minutes": 26,
        "title": "Scrape Sembcorp's transition targets",
        "prompt": (
            "Scrape Sembcorp Industries' latest sustainability disclosures and "
            "extract its transition targets with source links."
        ),
        # Captured verbatim from the deployed agent answering this exact prompt.
        # Do not hand-edit: re-run the prompt and paste the new reply instead, so the
        # showcase stays a real transcript rather than a written-up impression of one.
        "response": "**Sembcorp Industries has set a net-zero Scope 1 and 2 emissions target by 2050, with interim targets of 25GW gross installed renewables capacity by 2028 and emissions intensity of 0.26 tCO₂e/MWh by 2035 — though the 2028 intensity and 2030 absolute emissions targets have been withdrawn following the Alinta Energy acquisition.**\n\nBelow is the full set of transition targets extracted from Sembcorp's verified disclosures, with source links.\n\n---\n\n## Current Targets (post-Alinta acquisition, as of mid-2026)\n\n| Target | Metric | Deadline | Status |\n|--------|--------|----------|--------|\n| Gross installed renewables capacity | 25 GW | 2028 | On track (20.4 GW as of FY2025) |\n| Emissions intensity (Scope 1 & 2) | 0.26 tCO₂e/MWh | 2035 | Revised upward from 0.15; Alinta acquisition cited |\n| Net-zero emissions (Scope 1 & 2) | Absolute net-zero | 2050 | Unchanged |\n\n**Source:** [Sembcorp Climate Action Plan](https://www.sembcorp.com/om/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/) (verified, company website)\n\n> *\"In view of this acquisition, Sembcorp expects its emissions to increase in the near-term before declining. As such, Sembcorp will not meet its 2028 emissions intensity and 2030 absolute emissions targets.\"*\n\n---\n\n## Withdrawn / Superseded Targets\n\n| Target | Metric | Original Deadline | Reason for Change |\n|--------|--------|-------------------|-------------------|\n| Absolute emissions (Scope 1 & 2) | 2.7 million tCO₂e | 2030 | Withdrawn — Alinta acquisition increases near-term emissions |\n| Emissions intensity | 0.15 tCO₂e/MWh | 2028 | Revised to 0.26 by 2035 |\n\n**Source:** [Sembcorp Announces 2023-2028 Strategic Plan](https://www.sembcorp.com/news-and-insights/news/2023/sembcorp-announces-2023-2028-strategic-plan-to-drive-energy-transition/) (verified, company press release, November 2023)\n\n---\n\n## Achieved Milestones\n\n| Milestone | Metric | Achievement Year |\n|-----------|--------|------------------|\n| 2025 emissions intensity target (0.40 tCO₂e/MWh) | 0.27 tCO₂e/MWh achieved in 2024 | 2023 (early) |\n| 2025 gross installed renewables target (10 GW) | 13.1 GW achieved in 2024 | 2024 (early) |\n| Sustainable Financing KPI 1 (GHG intensity ≤ 0.40) | 0.27 tCO₂e/MWh | Met in 2023 |\n| Sustainable Financing KPI 3 (renewables ≥ 10 GW) | 13.1 GW | Surpassed in 2024 |\n\n**Source:** [Sembcorp Sustainability Report 2024](https://www.sembcorp.com/media/jc3bwis3/sci-sustainability-report-2024.pdf) (verified, company PDF), pages 44-45\n\n---\n\n## Capital Allocation Supporting Transition\n\n- **S$10.5 billion** (75% of 2024-2028 total investments) allocated to renewables\n- **10%** to hydrogen-ready assets\n- **10%** to decarbonisation solutions\n- **5%** to Integrated Urban Solutions\n\n**Source:** [Sembcorp Driving Energy Transition page](https://www.sembcorp.com/driving-energy-transition/) (verified, company website)\n\n---\n\n## Target-Setting Methodology\n\nSembcorp uses a country-specific lens with publicly available scenario datasets (IPCC AR6, NGFS, BloombergNEF, PRI Inevitable Policy Response). Country-level trajectories are weighted by Sembcorp's country concentration and aggregated to group level. The 2035 intensity target is set within a \"well below 2°C\" trajectory; the 2050 net-zero target is consistent with 1.5°C. The methodology has been independently assured on a limited basis by ERM CVS Australia.\n\n**Source:** [Sembcorp Climate Action Plan](https://www.sembcorp.com/om/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/)\n\n---\n\n## Key Document Links\n\n| Document | URL |\n|----------|-----|\n| Climate Action Plan (current targets) | https://www.sembcorp.com/om/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/ |\n| Sustainability Report 2024 | https://www.sembcorp.com/media/jc3bwis3/sci-sustainability-report-2024.pdf |\n| Annual Report 2025 | https://www.sembcorp.com/media/z2ypqfjj/sembcorp-ar25.pdf |\n| Annual Report 2024 | https://links.sgx.com/1.0.0/corporate-announcements/E3OPH06R1G42R3UK/838159_Sembcorp_Annual%20Report_2024.pdf |\n| 2023-2028 Strategic Plan Press Release | https://www.sembcorp.com/news-and-insights/news/2023/sembcorp-announces-2023-2028-strategic-plan-to-drive-energy-transition/ |\n| Driving Energy Transition overview | https://www.sembcorp.com/driving-energy-transition/ |\n| Sustainable Financing Framework (DNV SPO) | https://www.sembcorp.com/media/klgaf030/second-party-opinion-by-dnv.pdf |\n\n---\n\n## Key Takeaway for Analysts\n\nSembcorp's transition pathway has been materially disrupted by the A$6.5 billion Alinta Energy acquisition (completed June 2026). The company has explicitly withdrawn its 2028 intensity target (0.15 tCO₂e/MWh) and 2030 absolute emissions target (2.7 MtCO₂e), replacing them with a less ambitious 2035 intensity target of 0.26 tCO₂e/MWh. The 2050 net-zero commitment remains. The renewables capacity target of 25 GW by 2028 is still in place and on track (20.4 GW as of FY2025). Investors should monitor whether the Alinta integration leads to further target revisions in the next strategic review cycle.",
        "sources": [
            {
                "title": "sembcorp ar25",
                "url": "https://www.sembcorp.com/media/z2ypqfjj/sembcorp-ar25.pdf",
                "snippet": "Sembcorp Industries Annual Report 2025 As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition towards a sustainable and low-carbon future. We believe in building businesses that deliver long-term shareholder value and growth. Overview Group FY2025 Highlights 1 Our Presence 2...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "838159 Sembcorp Annual%20Report 2024",
                "url": "https://links.sgx.com/1.0.0/corporate-announcements/E3OPH06R1G42R3UK/838159_Sembcorp_Annual%20Report_2024.pdf",
                "snippet": "Sembcorp Industries Annual Report 2024 As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition towards a sustainable and low-carbon future. We believe in building businesses that deliver long-term shareholder value and growth. Overview Group FY2024 Highlights 1 Our Presence 2...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "Consolidated Financial Statements",
                "url": "https://media.sembcorp.com/data/cms/ar/ar2025/assets/pdf/Consolidated_Financial_Statements.pdf",
                "snippet": "...onsolidated Statement of Cash Flows 132 • Notes to the Financial Statements 135 Sembcorp and SDIC’s wind energy assets in Yunnan, China Sembcorp Industries Annual Report 2025 110 111 Overview Operating and Financial Review Our Leadership Other Information Consolidated Financial Statements Environmental, Social and Governance Review Consolidated Financial Sta...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "Directors Statement",
                "url": "https://media.sembcorp.com/data/cms/ar/ar2025/assets/pdf/Directors_Statement.pdf",
                "snippet": "We are pleased to submit this annual report to the members of the Company together with the audited financial statements for the financial year ended December 31, 2025. In our opinion: a. the financial statements set out on pages 124 to 251 are drawn up so as to give a True and fair view of the financial position of the Group and of the Company as at Decembe...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "Sembcorp AR2024 SinglePages",
                "url": "https://media.sembcorp.com/data/cms/ar/ar2024/assets/pdf/Sembcorp_AR2024_SinglePages.pdf",
                "snippet": "Sembcorp Industries Annual Report 2024 As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition towards a sustainable and low-carbon future. We believe in building businesses that deliver long-term shareholder value and growth. Overview Group FY2024 Highlights 1 Our Presence 2...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "sci sustainability report 2024",
                "url": "https://www.sembcorp.com/media/jc3bwis3/sci-sustainability-report-2024.pdf",
                "snippet": "Sembcorp’s wind assets located at Gujarat, India Our Sustainability Framework 40 Our Approach 42 • Reporting Framework • Materiality​ • Reporting Scope • Assurance • Supporting the Sustainable Development Goals • Sustainability Governance • Sustainability-linked Performance Incentives • Memberships and Associations Our Environmental, Social and Governance Pr...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "sembcorp ar2023",
                "url": "https://www.sembcorp.com/media/vhzjfn5u/sembcorp_ar2023.pdf",
                "snippet": "Sembcorp Industries Annual Report 2023 Sembcorp is a leading renewables player in Asia. We are committed to transforming our portfolio from brown to green and driving energy transition, creating lasting value for our stakeholders. Driving Energy Transition Overview Group FY2023 Highlights 2 Growing Market Opportunities 4 Leveraging Strengths 6 Climate Roadma...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "sustainability report",
                "url": "https://www.sembcorp.com/media/nhlbsvgy/sustainability_report.pdf",
                "snippet": "Sustainability Report Our Sustainability Framework​ 20 Our Approach to Sustainability​ 21 • Reporting Framework​ • Materiality ​ • Reporting Scope • Assurance • Supporting the Sustainable Development Goals • Sustainability Governance • Sustainability-linked Performance Incentives • Memberships and Associations​ Our Environmental, Social and Governance Priori...",
                "source": "bright_data+pdf",
                "sourceClass": "verified"
            },
            {
                "title": "Sembcorp Industries",
                "url": "https://ne-cdn.eurolandir.com/press-releases-attachments./4015966/Sembcorp-Industries_AR2025.pdf",
                "snippet": "As a leading energy player and an established industrial and urban solutions provider in Asia, Sembcorp plays a key role in the transition.Read more",
                "source": "bright_data_serp",
                "sourceClass": "non_verified"
            },
            {
                "title": "Sembcorp Industries Annual Report 2024",
                "url": "https://media.sembcorp.com/data/cms/ar/ar2024/index.html",
                "snippet": "Sustainability Report. Sembcorp has long held a strong commitment to sustainability, driven by our purpose to play our part in an inclusive energy transition.Read more",
                "source": "bright_data_serp",
                "sourceClass": "verified"
            }
        ],
        "tool_results": [
            {
                "name": "research_company_esg_news",
                "status": "ok",
                "summary": "Collected 8 company ESG/news references for: Sembcorp Industries",
                "sourceCount": 8
            },
            {
                "name": "web_search",
                "status": "ok",
                "summary": "Searched web for: Sembcorp Industries sustainability report 2024 transition targets climate",
                "sourceCount": 5
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped https://www.sembcorp.com/media/jc3bwis3/sci-sustainability-report-2024.pdf",
                "sourceCount": 1
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped https://www.sembcorp.com/media/z2ypqfjj/sembcorp-ar25.pdf",
                "sourceCount": 1
            },
            {
                "name": "web_search",
                "status": "ok",
                "summary": "Searched web for: Sembcorp Industries net zero 2050 2030 emissions reduction target site:sembcorp.com",
                "sourceCount": 5
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped https://www.sembcorp.com/om/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/",
                "sourceCount": 1
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped https://www.sembcorp.com/driving-energy-transition/",
                "sourceCount": 1
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped https://www.sembcorp.com/news-and-insights/news/2023/sembcorp-announces-2023-2028-strategic-plan-to-drive-energy-transition/",
                "sourceCount": 1
            },
            {
                "name": "get_validated_esg_evidence",
                "status": "ok",
                "summary": "Loaded 48 grouped claims and 24 sources for Sembcorp Industries.",
                "sourceCount": 24
            }
        ],
        "workflow_steps": [
            {
                "label": "Collected company ESG news",
                "status": "ok",
                "detail": "Collected 8 company ESG/news references for: Sembcorp Industries",
                "toolName": "research_company_esg_news"
            },
            {
                "label": "Searched web",
                "status": "ok",
                "detail": "Searched web for: Sembcorp Industries sustainability report 2024 transition targets climate",
                "toolName": "web_search"
            },
            {
                "label": "Scraped page",
                "status": "ok",
                "detail": "Scraped https://www.sembcorp.com/media/jc3bwis3/sci-sustainability-report-2024.pdf",
                "toolName": "scrape_url"
            },
            {
                "label": "Scraped page",
                "status": "ok",
                "detail": "Scraped https://www.sembcorp.com/media/z2ypqfjj/sembcorp-ar25.pdf",
                "toolName": "scrape_url"
            },
            {
                "label": "Searched web",
                "status": "ok",
                "detail": "Searched web for: Sembcorp Industries net zero 2050 2030 emissions reduction target site:sembcorp.com",
                "toolName": "web_search"
            },
            {
                "label": "Scraped page",
                "status": "ok",
                "detail": "Scraped https://www.sembcorp.com/om/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/",
                "toolName": "scrape_url"
            },
            {
                "label": "Scraped page",
                "status": "ok",
                "detail": "Scraped https://www.sembcorp.com/driving-energy-transition/",
                "toolName": "scrape_url"
            },
            {
                "label": "Scraped page",
                "status": "ok",
                "detail": "Scraped https://www.sembcorp.com/news-and-insights/news/2023/sembcorp-announces-2023-2028-strategic-plan-to-drive-energy-transition/",
                "toolName": "scrape_url"
            },
            {
                "label": "Get Validated Esg Evidence",
                "status": "ok",
                "detail": "Loaded 48 grouped claims and 24 sources for Sembcorp Industries.",
                "toolName": "get_validated_esg_evidence"
            }
        ],
        "report": None,
    },
)


def _seed_runtime_chat_history() -> None:
    if (
        DEFAULT_CHAT_HISTORY_DB != _BUNDLED_CHAT_HISTORY_DB
        and not DEFAULT_CHAT_HISTORY_DB.exists()
        and _BUNDLED_CHAT_HISTORY_DB.exists()
    ):
        DEFAULT_CHAT_HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_BUNDLED_CHAT_HISTORY_DB, DEFAULT_CHAT_HISTORY_DB)


_seed_runtime_chat_history()


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ChatSessionSummary(ApiModel):
    id: str
    title: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    message_count: int = Field(default=0, alias="messageCount")


class StoredChatMessage(ApiModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str = Field(alias="createdAt")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reference_articles: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="referenceArticles",
    )
    tool_results: list[dict[str, Any]] = Field(default_factory=list, alias="toolResults")
    workflow_steps: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="workflowSteps",
    )
    report: dict[str, Any] | None = None
    model: str | None = None
    page_context: dict[str, Any] = Field(default_factory=dict, alias="pageContext")


class ChatSessionDetail(ApiModel):
    session: ChatSessionSummary
    messages: list[StoredChatMessage]


class CreateChatSessionRequest(ApiModel):
    title: str | None = None


class ChatHistoryStore:
    def __init__(
        self,
        path: Path | str = DEFAULT_CHAT_HISTORY_DB,
        *,
        curate_showcase: bool | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        should_curate = (
            self.path.resolve() == DEFAULT_CHAT_HISTORY_DB.resolve()
            if curate_showcase is None
            else curate_showcase
        )
        if should_curate:
            self._curate_showcase_history()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    page_context_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id)
                        ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    reference_articles_json TEXT NOT NULL DEFAULT '[]',
                    tool_results_json TEXT NOT NULL DEFAULT '[]',
                    workflow_steps_json TEXT NOT NULL DEFAULT '[]',
                    report_json TEXT,
                    model TEXT,
                    page_context_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                    ON chat_messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
                    ON chat_sessions(updated_at DESC);
                """
            )

    def _curate_showcase_history(self) -> None:
        # The curated chats are content, and this module is their only source of truth, so
        # the current ones are dropped and rebuilt on every boot alongside the retired ids.
        # Without this the INSERTs below are OR IGNORE against rows that already exist on
        # the deployed volume, and an edited prompt or answer would never reach production.
        stale_ids = LEGACY_SHOWCASE_SESSION_IDS + tuple(
            chat["id"] for chat in SHOWCASE_CHATS
        )
        placeholders = ",".join("?" for _ in stale_ids)
        now = datetime.now(timezone.utc)

        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM chat_messages WHERE session_id IN ({placeholders})",
                stale_ids,
            )
            connection.execute(
                f"DELETE FROM chat_sessions WHERE id IN ({placeholders})",
                stale_ids,
            )

            for chat in SHOWCASE_CHATS:
                created_at = now - timedelta(minutes=chat["age_minutes"])
                updated_at = created_at + timedelta(minutes=1)
                page_context = {
                    "route": "assistant",
                    "showcase": True,
                    "capability": chat["id"].removeprefix("session-showcase-"),
                    "company": {
                        "id": "U96",
                        "name": "Sembcorp Industries",
                        "ticker": "U96.SI",
                    },
                }
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_sessions (
                        id, title, created_at, updated_at, page_context_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chat["id"],
                        chat["title"],
                        created_at.isoformat(),
                        updated_at.isoformat(),
                        json_dump(page_context),
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_messages (
                        id, session_id, role, content, created_at,
                        sources_json, reference_articles_json, tool_results_json,
                        workflow_steps_json, report_json, model, page_context_json
                    ) VALUES (?, ?, 'user', ?, ?, '[]', '[]', '[]', '[]',
                              NULL, NULL, ?)
                    """,
                    (
                        f"msg-{chat['id']}-prompt",
                        chat["id"],
                        chat["prompt"],
                        created_at.isoformat(),
                        json_dump(page_context),
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_messages (
                        id, session_id, role, content, created_at,
                        sources_json, reference_articles_json, tool_results_json,
                        workflow_steps_json, report_json, model, page_context_json
                    ) VALUES (?, ?, 'assistant', ?, ?, ?, '[]', ?, ?, ?, ?, ?)
                    """,
                    (
                        f"msg-{chat['id']}-response",
                        chat["id"],
                        chat["response"],
                        updated_at.isoformat(),
                        json_dump(chat["sources"]),
                        json_dump(chat["tool_results"]),
                        json_dump(chat["workflow_steps"]),
                        json_dump(chat["report"]) if chat["report"] else None,
                        "PolyFintech ESG agent",
                        json_dump(page_context),
                    ),
                )

    def create_session(self, title: str | None = None, session_id: str | None = None) -> ChatSessionSummary:
        now = now_iso()
        resolved_id = session_id or f"session-{uuid.uuid4().hex}"
        resolved_title = clean_title(title) or "New ESG chat"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_sessions
                    (id, title, created_at, updated_at, page_context_json)
                VALUES (?, ?, ?, ?, '{}')
                """,
                (resolved_id, resolved_title, now, now),
            )
        return self.get_session_summary(resolved_id)

    def ensure_session(self, session_id: str | None, title: str | None = None) -> ChatSessionSummary:
        if not session_id:
            return self.create_session(title=title)
        existing = self.get_session_summary_or_none(session_id)
        if existing:
            return existing
        return self.create_session(title=title, session_id=session_id)

    def list_sessions(self) -> list[ChatSessionSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                    COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [session_from_row(row) for row in rows]

    def get_session(self, session_id: str) -> ChatSessionDetail:
        session = self.get_session_summary_or_none(session_id)
        if not session:
            raise KeyError(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return ChatSessionDetail(
            session=session,
            messages=[message_from_row(row) for row in rows],
        )

    def get_session_summary(self, session_id: str) -> ChatSessionSummary:
        summary = self.get_session_summary_or_none(session_id)
        if not summary:
            raise KeyError(session_id)
        return summary

    def get_session_summary_or_none(self, session_id: str) -> ChatSessionSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                    COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                """,
                (session_id,),
            ).fetchone()
        return session_from_row(row) if row else None

    def append_user_message(
        self,
        session_id: str,
        content: str,
        page_context: dict[str, Any],
        message_id: str | None = None,
    ) -> StoredChatMessage:
        session = self.ensure_session(session_id)
        message = self._insert_message(
            session_id=session.id,
            role="user",
            content=content,
            page_context=page_context,
            message_id=message_id,
        )
        if session.title == "New ESG chat":
            self.rename_session(session.id, title_from_content(content))
        self.touch_session(session.id, page_context=page_context)
        return message

    def append_assistant_response(
        self,
        session_id: str,
        response: AssistantResponse,
        page_context: dict[str, Any],
    ) -> StoredChatMessage:
        message = self._insert_message(
            session_id=session_id,
            role=response.message.role,
            content=response.message.content,
            page_context=page_context,
            sources=[item.model_dump(by_alias=True) for item in response.sources],
            reference_articles=[
                item.model_dump(by_alias=True) for item in response.reference_articles
            ],
            tool_results=[item.model_dump(by_alias=True) for item in response.tool_results],
            workflow_steps=[
                item.model_dump(by_alias=True) for item in response.workflow_steps
            ],
            report=response.report.model_dump(by_alias=True) if response.report else None,
            model=response.model,
        )
        self.touch_session(session_id, page_context=page_context)
        return message

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            cursor = connection.execute(
                "DELETE FROM chat_sessions WHERE id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    def rename_session(self, session_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                (clean_title(title) or "New ESG chat", now_iso(), session_id),
            )

    def touch_session(self, session_id: str, page_context: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?, page_context_json = ?
                WHERE id = ?
                """,
                (now_iso(), json_dump(page_context), session_id),
            )

    def _insert_message(
        self,
        session_id: str,
        role: Literal["user", "assistant"],
        content: str,
        page_context: dict[str, Any],
        message_id: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        reference_articles: list[dict[str, Any]] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        workflow_steps: list[dict[str, Any]] | None = None,
        report: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> StoredChatMessage:
        created_at = now_iso()
        resolved_id = message_id or f"msg-{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (
                    id, session_id, role, content, created_at,
                    sources_json, reference_articles_json, tool_results_json,
                    workflow_steps_json, report_json, model, page_context_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_id,
                    session_id,
                    role,
                    content,
                    created_at,
                    json_dump(sources or []),
                    json_dump(reference_articles or []),
                    json_dump(tool_results or []),
                    json_dump(workflow_steps or []),
                    json_dump(report) if report else None,
                    model,
                    json_dump(page_context),
                ),
            )
        return StoredChatMessage(
            id=resolved_id,
            role=role,
            content=content,
            created_at=created_at,
            sources=sources or [],
            reference_articles=reference_articles or [],
            tool_results=tool_results or [],
            workflow_steps=workflow_steps or [],
            report=report,
            model=model,
            page_context=page_context,
        )


def session_from_row(row: sqlite3.Row) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=int(row["message_count"]),
    )


def message_from_row(row: sqlite3.Row) -> StoredChatMessage:
    return StoredChatMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        sources=json_load(row["sources_json"], []),
        reference_articles=json_load(row["reference_articles_json"], []),
        tool_results=json_load(row["tool_results_json"], []),
        workflow_steps=json_load(row["workflow_steps_json"], []),
        report=json_load(row["report_json"], None) if row["report_json"] else None,
        model=row["model"],
        page_context=json_load(row["page_context_json"], {}),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re_space(value)
    return cleaned[:72] if cleaned else None


def title_from_content(content: str) -> str:
    cleaned = re_space(content)
    if not cleaned:
        return "New ESG chat"
    return cleaned[:56]


def re_space(value: str) -> str:
    return " ".join(value.strip().split())


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_load(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def chat_message_from_stored(message: StoredChatMessage) -> ChatMessage:
    return ChatMessage(role=message.role, content=message.content)
