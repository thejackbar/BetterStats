import { Outlet } from 'react-router-dom'
import ScoutModuleLayout from './ScoutModuleLayout'

// Route wrapper — every /betterscout/app/* page renders inside the shared
// module shell. Individual screens pass title/caption/filters/stats/actions
// up via their own header slots (see ScoutModuleLayout for the props), the
// same pattern every other Better module's screens already use.
export default function ScoutLayout() {
  return (
    <ScoutModuleLayout>
      <Outlet />
    </ScoutModuleLayout>
  )
}
