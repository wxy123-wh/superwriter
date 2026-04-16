export interface Foreshadow {
  id: string;
  title: string;
  description: string;
  status: "pending" | "resolved" | "abandoned";
  importance: "high" | "medium" | "low";
  plantedChapter: number;
  resolvedChapter?: number;
  keywords: string[];
  createdAt: string;
  updatedAt: string;
}

export type ForeshadowStatus = Foreshadow["status"];
export type ForeshadowImportance = Foreshadow["importance"];
