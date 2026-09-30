import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AssistantPage, DataQualityPage, EHRIntegrationPage, EvidencePage, MonitoringPage, OverviewPage, PatientsPage, RiskPage } from "./pages";

export default function App() {
  return <Routes><Route element={<Layout />}><Route index element={<OverviewPage />} /><Route path="patients" element={<PatientsPage />} /><Route path="risk" element={<RiskPage />} /><Route path="evidence" element={<EvidencePage />} /><Route path="assistant" element={<AssistantPage />} /><Route path="quality" element={<DataQualityPage />} /><Route path="monitoring" element={<MonitoringPage />} /><Route path="ehr" element={<EHRIntegrationPage />} /><Route path="*" element={<Navigate replace to="/" />} /></Route></Routes>;
}
