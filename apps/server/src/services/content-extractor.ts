/**
 * Content Extractor Service
 * Extracts structured information from chapter content
 */

export interface ExtractedContent {
  characters: string[];
  locations: string[];
  timeMarkers: string[];
  objectMentions: string[];
}

/**
 * Common location names for extraction
 */
const LOCATION_PATTERNS = [
  '城堡', '宫殿', '城市', '城镇', '村庄', '森林', '山脉', '河流', '海洋', '湖泊',
  '房屋', '房间', '厨房', '卧室', '书房', '大厅', '走廊', '门口', '街道', '市场',
  '酒馆', '教堂', '寺庙', '墓地', '山洞', '沙漠', '草原', '岛屿', '港口', '码头',
  ' castle', 'palace', 'city', 'town', 'village', 'forest', 'mountain', 'river', 'ocean', 'lake',
  'house', 'room', 'kitchen', 'bedroom', 'study', 'hall', 'corridor', 'door', 'street', 'market',
  'inn', 'church', 'temple', 'graveyard', 'cave', 'desert', 'meadow', 'island', 'port', 'dock',
];

/**
 * Time marker patterns
 */
const TIME_PATTERNS = [
  /\d+\s*(年|月|日|小时|分钟|秒|世纪|年代|时代)/g,
  /春|夏|秋|冬/g,
  /早晨|中午|下午|晚上|深夜|黎明|黄昏/g,
  /昨天|今天|明天|后天|前天/g,
  /\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?/g,
  /(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+/gi,
  /(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)/gi,
  /(morning|afternoon|evening|night|dawn|dusk|noon|midnight)/gi,
  /(yesterday|today|tomorrow)/gi,
  /year\s+\d+/gi,
];

/**
 * Common object/item patterns
 */
const OBJECT_PATTERNS = [
  /(?:剑|刀|武器|盔甲|盾牌|戒指|项链|盒子|箱子|书|信件|日记|地图|钥匙|宝箱)/g,
  /(?:sword|knife|weapon|armor|shield|ring|necklace|box|chest|book|letter|diary|map|key|treasure)/gi,
  /(?:took|grabbed|held|carried|possessed|owned)\s+[^.。,，]+/g,
];

/**
 * Extract character names from content
 * Simple heuristic: capitalized words that appear multiple times
 */
function extractCharacters(content: string): string[] {
  const characterNames: Set<string> = new Set();

  // Pattern for Chinese names (2-4 characters)
  const chineseNamePattern = /[A-Z\u4e00-\u9fa5][A-Z\u4e00-\u9fa5]{1,3}(?=\s*[A-Z\u4e00-\u9fa5]|$)/g;

  // Find all potential Chinese names
  const chineseMatches = content.match(chineseNamePattern);
  if (chineseMatches) {
    chineseMatches.forEach(name => {
      if (name.length >= 2 && name.length <= 4) {
        characterNames.add(name);
      }
    });
  }

  // Pattern for English names (capitalized words)
  const englishNamePattern = /\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b/g;
  const englishMatches = content.match(englishNamePattern);
  if (englishMatches) {
    englishMatches.forEach(name => {
      if (name.split(/\s+/).length <= 3) {
        characterNames.add(name);
      }
    });
  }

  return Array.from(characterNames);
}

/**
 * Extract locations from content
 */
function extractLocations(content: string): string[] {
  const locations: Set<string> = new Set();

  for (const pattern of LOCATION_PATTERNS) {
    const regex = typeof pattern === 'string' ? new RegExp(pattern, 'g') : pattern;
    const matches = content.match(regex);
    if (matches) {
      matches.forEach(loc => locations.add(loc));
    }
  }

  // Additional pattern: "在X" or "at/in X"
  const locationPhrasePattern = /(?:在|来到|走向|进入|离开|到达)([^\s，。,.！!？?]{2,10})/g;
  let match;
  while ((match = locationPhrasePattern.exec(content)) !== null) {
    const loc = match[1].trim();
    if (loc.length >= 2) {
      locations.add(loc);
    }
  }

  return Array.from(locations);
}

/**
 * Extract time markers from content
 */
function extractTimeMarkers(content: string): string[] {
  const timeMarkers: Set<string> = new Set();

  for (const pattern of TIME_PATTERNS) {
    if (typeof pattern === 'string') {
      const regex = new RegExp(pattern, 'g');
      let match;
      while ((match = regex.exec(content)) !== null) {
        timeMarkers.add(match[0]);
      }
    } else {
      const matches = content.match(pattern);
      if (matches) {
        matches.forEach(t => timeMarkers.add(t));
      }
    }
  }

  return Array.from(timeMarkers);
}

/**
 * Extract object mentions from content
 */
function extractObjectMentions(content: string): string[] {
  const objects: Set<string> = new Set();

  for (const pattern of OBJECT_PATTERNS) {
    if (typeof pattern === 'string') {
      const regex = new RegExp(pattern, 'g');
      let match;
      while ((match = regex.exec(content)) !== null) {
        objects.add(match[0]);
      }
    } else {
      const matches = content.match(pattern);
      if (matches) {
        matches.forEach(o => objects.add(o.trim()));
      }
    }
  }

  return Array.from(objects);
}

/**
 * Main extraction function
 */
export function extractContent(content: string): ExtractedContent {
  return {
    characters: extractCharacters(content),
    locations: extractLocations(content),
    timeMarkers: extractTimeMarkers(content),
    objectMentions: extractObjectMentions(content),
  };
}
