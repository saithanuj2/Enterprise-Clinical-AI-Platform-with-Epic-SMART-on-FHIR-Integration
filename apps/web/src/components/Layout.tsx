import { NavLink, Outlet } from "react-router-dom";

const navigation = [["/", "Executive overview", "OV"], ["/patients", "Patient explorer", "PT"], ["/risk", "Readmission risk", "RX"], ["/evidence", "Clinical search", "CS"], ["/assistant", "AI assistant", "AI"], ["/quality", "Data quality", "DQ"], ["/monitoring", "Model monitoring", "MM"], ["/ehr", "Epic EHR integration", "EH"]] as const;

export function Layout() {
  return <div className="shell"><aside><div className="brand"><span>MN</span><strong>MedNexus AI</strong></div><nav aria-label="Primary navigation">{navigation.map(([path, label, icon]) => <NavLink end={path === "/"} key={path} to={path}><b aria-hidden="true">{icon}</b>{label}</NavLink>)}</nav><div className="safety">Research use only<br /><small>Deidentified MIMIC-IV demo</small></div></aside><main id="main-content"><Outlet /><footer>Not for diagnosis or direct patient care. Demonstration results require external clinical validation.</footer></main></div>;
}
