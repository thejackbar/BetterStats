// Club-facing BetterCRM vocabulary — overrides the shared Kanban/detail
// components' default sales language (Won/Lost/"deal") with plain words a
// volunteer club officer already uses. The Super Admin sales pipeline
// (pages/admin/SuperCrm.jsx) deliberately keeps the defaults instead — see
// ui.jsx's DEFAULT_CRM_TERMS for the reasoning.
export const SPONSOR_TERMS = {
  won: 'Signed',
  lost: 'Not Proceeding',
  itemSingular: 'sponsor',
  itemPlural: 'sponsors',
  titleLabel: 'Sponsor name',
}
