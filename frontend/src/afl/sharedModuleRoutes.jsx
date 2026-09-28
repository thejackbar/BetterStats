import { lazy } from 'react'
import { Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '../components/ProtectedRoute'

// BetterAdmin and BetterSocials in the football app are the cricket screens
// themselves, not copies: the same pages, on the same URLs, talking to the same
// routers the football backend now mounts (afl_main.py). They render inside the
// shared ModuleLayout, which reads lib/sport.js to drop the cricket-only chrome.
//
// Each page is lazy, so the football bundle only loads a module screen when
// somebody opens it, and a club without the module never downloads it at all.
// These sit beside the football admin layout rather than inside it: each
// module surface carries its own sidebar, exactly as it does in cricket.
//
// Called as a function, not rendered as a component: <Routes> only accepts
// <Route> children, so a component wrapping them would not be matched.

const ClubhouseToday = lazy(() => import('../pages/admin/clubhouse/ClubhouseToday'))
const ClubhouseSegments = lazy(() => import('../pages/admin/clubhouse/SegmentsRoute'))
const ClubhouseIntegrations = lazy(() => import('../pages/admin/clubhouse/ClubhouseIntegrations'))
const ClubhouseReports = lazy(() => import('../pages/admin/clubhouse/ClubhouseReports'))
const ClubhouseSettings = lazy(() => import('../pages/admin/clubhouse/ClubhouseSettings'))
const ClubManagerApp = lazy(() => import('../pages/admin/clubmanager/redesign/ClubManagerApp'))
const AdminCommittee = lazy(() => import('../pages/admin/AdminCommittee'))
const MeetingRoom = lazy(() => import('../pages/admin/MeetingRoom'))
const AdminEvents = lazy(() => import('../pages/admin/AdminEvents'))
const AdminAssets = lazy(() => import('../pages/admin/AdminAssets'))
const AdminClubDiary = lazy(() => import('../pages/admin/AdminClubDiary'))
const AdminQualifications = lazy(() => import('../pages/admin/AdminQualifications'))
const AdminVolunteers = lazy(() => import('../pages/admin/AdminVolunteers'))
const AdminFamilies = lazy(() => import('../pages/admin/AdminFamilies'))
const AdminFeesMembers = lazy(() => import('../pages/admin/AdminFeesMembers'))
const AdminFeeSchedule = lazy(() => import('../pages/admin/AdminFeeSchedule'))
const AdminFeePayments = lazy(() => import('../pages/admin/AdminFeePayments'))
const AdminFeePaymentImport = lazy(() => import('../pages/admin/AdminFeePaymentImport'))
const AdminFeeBulkPayment = lazy(() => import('../pages/admin/AdminFeeBulkPayment'))
const AdminFeeReports = lazy(() => import('../pages/admin/AdminFeeReports'))
const AdminFeesSquare = lazy(() => import('../pages/admin/AdminFeesSquare'))
const AdminFeesXero = lazy(() => import('../pages/admin/AdminFeesXero'))
const AdminMembershipTypes = lazy(() => import('../pages/admin/AdminMembershipTypes'))
const AdminFeeMemberDetail = lazy(() => import('../pages/admin/AdminFeeMemberDetail'))
const BetterMerchHome = lazy(() => import('../pages/admin/bettermerch/BetterMerchHome'))
const MerchStock = lazy(() => import('../pages/admin/bettermerch/MerchStock'))
const MerchActivity = lazy(() => import('../pages/admin/bettermerch/MerchActivity'))
const MerchReports = lazy(() => import('../pages/admin/bettermerch/MerchReports'))
const MerchSquare = lazy(() => import('../pages/admin/bettermerch/MerchSquare'))
const MerchOrders = lazy(() => import('../pages/admin/bettermerch/MerchOrders'))
const BetterCrmHome = lazy(() => import('../pages/admin/bettercrm/BetterCrmHome'))
const BetterCrmPeople = lazy(() => import('../pages/admin/bettercrm/BetterCrmPeople'))
const BetterCrmTracker = lazy(() => import('../pages/admin/bettercrm/BetterCrmTracker'))
const CommsCampaigns = lazy(() => import('../pages/admin/bettercomms/CommsCampaigns'))
const CommsContacts = lazy(() => import('../pages/admin/bettercomms/CommsContacts'))
const CommsTemplates = lazy(() => import('../pages/admin/bettercomms/CommsTemplates'))
const CommsSettings = lazy(() => import('../pages/admin/bettercomms/CommsSettings'))

const P = (el, props = {}) => <ProtectedRoute {...props}>{el}</ProtectedRoute>
const CM = screen => P(<ClubManagerApp initialScreen={screen} />)

export function betterAdminRoutes() {
  return [
    <Route key="ch" path="/admin/clubhouse" element={P(<ClubhouseToday />)} />,
    <Route key="ch-int" path="/admin/clubhouse/integrations" element={P(<ClubhouseIntegrations />)} />,
    <Route key="ch-rep" path="/admin/clubhouse/reports" element={P(<ClubhouseReports />)} />,
    <Route key="ch-set" path="/admin/clubhouse/settings" element={P(<ClubhouseSettings />)} />,
    <Route key="ch-dir" path="/admin/clubhouse/directory" element={CM('directory')} />,
    <Route key="ch-ros" path="/admin/clubhouse/roster" element={CM('roster')} />,
    <Route key="ch-ar" path="/admin/clubhouse/areas-roles" element={CM('setup')} />,
    <Route key="ch-rp" path="/admin/clubhouse/role-programs" element={CM('role_programs')} />,
    <Route key="ch-cm" path="/admin/clubhouse/committee/manage" element={P(<AdminCommittee />)} />,
    <Route key="ch-mr" path="/admin/clubhouse/committee/meeting/:meetingId" element={P(<MeetingRoom />)} />,
    <Route key="ch-em" path="/admin/clubhouse/events/manage" element={P(<AdminEvents />)} />,
    <Route key="ch-fm" path="/admin/clubhouse/facilities/manage" element={P(<AdminAssets />)} />,
    <Route key="ch-dm" path="/admin/clubhouse/diary/manage" element={P(<AdminClubDiary />)} />,
    <Route key="ch-q" path="/admin/clubhouse/directory/qualifications" element={P(<AdminQualifications />)} />,
    <Route key="ch-v" path="/admin/clubhouse/directory/volunteers" element={P(<AdminVolunteers />)} />,
    <Route key="ch-fam" path="/admin/clubhouse/directory/families" element={<Navigate to="/admin/families" replace />} />,
    <Route key="ba" path="/admin/betteradmin" element={<Navigate to="/admin/clubhouse" replace />} />,
    <Route key="fam" path="/admin/families" element={P(<AdminFamilies />)} />,
    <Route key="com" path="/admin/committee" element={CM('committee')} />,
    <Route key="vol" path="/admin/volunteers" element={CM('directory')} />,
    <Route key="rol" path="/admin/roles" element={CM('setup')} />,
    <Route key="act" path="/admin/activities" element={CM('setup')} />,
    <Route key="qual" path="/admin/qualifications" element={CM('directory')} />,
    <Route key="ev" path="/admin/events" element={CM('events')} />,
    <Route key="as" path="/admin/assets" element={CM('facilities')} />,
    <Route key="di" path="/admin/club-diary" element={CM('diary')} />,

    <Route key="fees" path="/admin/fees" element={P(<AdminFeesMembers />, { requireModule: 'fees' })} />,
    <Route key="fees-s" path="/admin/fees/schedule" element={P(<AdminFeeSchedule />, { requireModule: 'fees' })} />,
    <Route key="fees-p" path="/admin/fees/payments" element={P(<AdminFeePayments />, { requireModule: 'fees' })} />,
    <Route key="fees-pi" path="/admin/fees/payments/import" element={P(<AdminFeePaymentImport />, { requireModule: 'fees' })} />,
    <Route key="fees-pb" path="/admin/fees/payments/bulk" element={P(<AdminFeeBulkPayment />, { requireModule: 'fees' })} />,
    <Route key="fees-r" path="/admin/fees/reports" element={P(<AdminFeeReports />, { requireModule: 'fees' })} />,
    <Route key="fees-sq" path="/admin/fees/square" element={P(<AdminFeesSquare />, { requireModule: 'fees' })} />,
    <Route key="fees-x" path="/admin/fees/xero" element={P(<AdminFeesXero />, { requireModule: 'fees' })} />,
    <Route key="fees-mt" path="/admin/fees/membership-types" element={P(<AdminMembershipTypes />, { requireModule: 'fees' })} />,
    <Route key="fees-m" path="/admin/fees/member/:memberId" element={P(<AdminFeeMemberDetail />, { requireModule: 'fees' })} />,

    <Route key="m" path="/admin/merch" element={P(<BetterMerchHome />, { requireModule: 'merch' })} />,
    <Route key="m-s" path="/admin/merch/stock" element={P(<MerchStock />, { requireModule: 'merch' })} />,
    <Route key="m-e" path="/admin/merch/equipment" element={<Navigate to="/admin/assets" replace />} />,
    <Route key="m-a" path="/admin/merch/activity" element={P(<MerchActivity />, { requireModule: 'merch' })} />,
    <Route key="m-r" path="/admin/merch/reports" element={P(<MerchReports />, { requireModule: 'merch' })} />,
    <Route key="m-sq" path="/admin/merch/square" element={P(<MerchSquare />, { requireModule: 'merch' })} />,
    <Route key="m-o" path="/admin/merch/orders" element={P(<MerchOrders />, { requireModule: 'merch' })} />,

    <Route key="crm" path="/admin/crm" element={P(<BetterCrmHome />, { requireModule: 'crm' })} />,
    <Route key="crm-p" path="/admin/crm/people" element={P(<BetterCrmPeople />, { requireModule: 'crm' })} />,
    <Route key="crm-t" path="/admin/crm/:pipelineId" element={P(<BetterCrmTracker />, { requireModule: 'crm' })} />,

    <Route key="c" path="/admin/comms" element={P(<CommsCampaigns />, { requireModule: 'comms' })} />,
    <Route key="c-seg" path="/admin/comms/segments" element={P(<ClubhouseSegments />, { requireModule: 'comms' })} />,
    <Route key="c-con" path="/admin/comms/contacts" element={P(<CommsContacts />, { requireModule: 'comms' })} />,
    <Route key="c-l" path="/admin/comms/lists" element={<Navigate to="/admin/comms/segments" replace />} />,
    <Route key="c-t" path="/admin/comms/templates" element={P(<CommsTemplates />, { requireModule: 'comms' })} />,
    <Route key="c-set" path="/admin/comms/settings" element={P(<CommsSettings />, { requireModule: 'comms' })} />,
    <Route key="c-id" path="/admin/comms/:id" element={P(<CommsCampaigns />, { requireModule: 'comms' })} />,
  ]
}
