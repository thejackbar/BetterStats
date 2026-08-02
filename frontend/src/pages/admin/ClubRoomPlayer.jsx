import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import ClubRoomStage from './ClubRoomStage'

// The authenticated admin preview — "Launch on this screen" from
// /admin/club-room. All the actual slideshow rendering lives in
// ClubRoomStage, shared with the public PIN-gated link (PublicClubRoom.jsx);
// this wrapper only supplies where the data comes from and where Esc/"back
// to setup" goes. No surrounding app chrome (this route isn't wrapped in
// BetterStatsLayout, see App.jsx), so a refresh lands straight back on the
// show.
export default function ClubRoomPlayer() {
  const navigate = useNavigate()
  return <ClubRoomStage fetchPlay={api.clubRoomPlay} onExit={() => navigate('/admin/club-room')} />
}
