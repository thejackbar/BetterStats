import { useState, useEffect, useRef, useCallback } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { api } from '../../lib/api'
import {
  T1_HeroList, T2_CardGrid, T3_SideNumbered, T4_BattingOrder,
  T5_Brutalist, T6_Diagonal, T7_CaptainSpotlight, T8_Mosaic, T9_Flyer,
  C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore,
  SC1_Broadcast, SC2_Brutalist, SC3_Dashboard,
  PALETTES, orgToPalette,
} from '../../social/cricket-templates'