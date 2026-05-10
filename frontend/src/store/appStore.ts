import { create } from 'zustand';
import type { Dataset } from '../data/mockData';

interface AppState {
  // Search and discovery
  searchQuery: string;
  selectedDomain: string | null;
  setSearchQuery: (query: string) => void;
  setSelectedDomain: (domain: string | null) => void;

  // Dataset selection
  selectedDataset: Dataset | null;
  setSelectedDataset: (dataset: Dataset | null) => void;

  // Navigation
  currentPage: string;
  setCurrentPage: (page: string) => void;

  // UI state
  isSidebarCollapsed: boolean;
  toggleSidebar: () => void;
  isInsightsPanelOpen: boolean;
  toggleInsightsPanel: () => void;

  // Loading states
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  // Agent activity
  isAgentActive: boolean;
  agentStatus: string;
  setAgentStatus: (status: string, active?: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Search and discovery
  searchQuery: '',
  selectedDomain: null,
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSelectedDomain: (domain) => set({ selectedDomain: domain }),

  // Dataset selection
  selectedDataset: null,
  setSelectedDataset: (dataset) => set({ selectedDataset: dataset }),

  // Navigation
  currentPage: 'home',
  setCurrentPage: (page) => set({ currentPage: page }),

  // UI state
  isSidebarCollapsed: false,
  toggleSidebar: () => set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),
  isInsightsPanelOpen: true,
  toggleInsightsPanel: () => set((state) => ({ isInsightsPanelOpen: !state.isInsightsPanelOpen })),

  // Loading states
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),

  // Agent activity
  isAgentActive: false,
  agentStatus: 'Idle',
  setAgentStatus: (status, active = true) => set({ agentStatus: status, isAgentActive: active }),
}));
