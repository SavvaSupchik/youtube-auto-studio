import { Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import ProjectView from "./pages/ProjectView";
import NewVideo from "./pages/NewVideo";
import VideoView from "./pages/VideoView";
import Voices from "./pages/Voices";
import Settings from "./pages/Settings";
import { Music } from "./pages/Music";
import NicheAnalysis from "./pages/NicheAnalysis";

export default function App() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects/:projectId" element={<ProjectView />} />
          <Route path="/projects/:projectId/new" element={<NewVideo />} />
          <Route path="/videos/:videoId" element={<VideoView />} />
          <Route path="/voices" element={<Voices />} />
          <Route path="/music" element={<Music />} />
          <Route path="/niches" element={<NicheAnalysis />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
