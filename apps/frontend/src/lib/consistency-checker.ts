/**
 * Consistency Checker
 * Validates chapter content against previous snapshots and novel manifest
 */

import type { ChapterSnapshot, ConsistencyIssue, NovelManifest } from '../types/chapter-snapshot';

export function checkConsistency(
  currentChapter: number,
  snapshot: ChapterSnapshot,
  manifest: NovelManifest
): ConsistencyIssue[] {
  const issues: ConsistencyIssue[] = [];

  // Check character states against manifest
  for (const charState of snapshot.characterStates) {
    const manifestChar = manifest.characters.find(c => c.characterId === charState.characterId);

    if (manifestChar) {
      // Check if character's location matches their default location when they should be there
      if (charState.location && manifestChar.defaultLocation) {
        if (charState.location !== manifestChar.defaultLocation) {
          // This is informational - characters can be in different locations
        }
      }

      // Check for status inconsistencies
      if (charState.status === 'dead' && manifestChar) {
        // Character marked as dead - could be an issue if they appear later
        // This would be caught by checking subsequent chapters
      }
    }

    // Check for unknown status
    if (charState.status === 'unknown' && currentChapter > 1) {
      issues.push({
        type: 'character_conflict',
        severity: 'warning',
        message: `角色 "${charState.name}" 在第 ${currentChapter} 章状态未知`,
        chapter: currentChapter,
        details: { characterId: charState.characterId },
      });
    }
  }

  // Check world state consistency
  const worldState = snapshot.worldState;

  // Timeline progression check
  if (currentChapter > 1 && worldState.currentTimeline) {
    // If there's a clear timeline marker, ensure it makes sense
    // This is a basic check - more sophisticated timeline tracking could be added
  }

  // Active conflicts should be tracked
  if (worldState.activeConflicts.length === 0 && currentChapter > 1) {
    // Might indicate missing conflict tracking - this is informational
  }

  // Check pending mysteries count
  if (worldState.pendingMysteries < 0) {
    issues.push({
      type: 'timeline_error',
      severity: 'error',
      message: `第 ${currentChapter} 章的待解决谜团数量无效`,
      chapter: currentChapter,
      details: { count: worldState.pendingMysteries },
    });
  }

  return issues;
}

/**
 * Compare current snapshot with previous to detect issues
 */
export function compareWithPrevious(
  currentSnapshot: ChapterSnapshot,
  previousSnapshot: ChapterSnapshot | null
): ConsistencyIssue[] {
  const issues: ConsistencyIssue[] = [];

  if (!previousSnapshot) {
    return issues;
  }

  // Check for character location changes that might be inconsistent
  for (const currentChar of currentSnapshot.characterStates) {
    const previousChar = previousSnapshot.characterStates.find(
      c => c.characterId === currentChar.characterId
    );

    if (previousChar) {
      // Character was in one location, now in another - check if it's plausible
      if (previousChar.location && currentChar.location &&
          previousChar.location !== currentChar.location) {
        // Location changed - could be travel, which is fine
        // Could add logic to check if the distance is plausible
      }

      // Check for status changes from alive to dead
      if (previousChar.status === 'alive' && currentChar.status === 'dead') {
        // This is expected when a character dies - no issue
      }

      // Check for impossible revivals
      if (previousChar.status === 'dead' && currentChar.status === 'alive') {
        issues.push({
          type: 'character_conflict',
          severity: 'error',
          message: `角色 "${currentChar.name}" 在第 ${currentSnapshot.chapterNumber} 章被标记为死亡但现在存活`,
          chapter: currentSnapshot.chapterNumber,
          details: {
            characterId: currentChar.characterId,
            previousStatus: previousChar.status,
            currentStatus: currentChar.status,
          },
        });
      }

      // Check for unknown status transition
      if (previousChar.status !== 'unknown' && currentChar.status === 'unknown') {
        issues.push({
          type: 'character_conflict',
          severity: 'warning',
          message: `角色 "${currentChar.name}" 的状态在第 ${currentSnapshot.chapterNumber} 章变为未知`,
          chapter: currentSnapshot.chapterNumber,
          details: { characterId: currentChar.characterId },
        });
      }
    }
  }

  // Check that secrets revealed don't get "un-revealed"
  for (const secret of currentSnapshot.worldState.revealedSecrets) {
    if (!previousSnapshot.worldState.revealedSecrets.includes(secret)) {
      // This is fine - new secrets can be revealed
    }
  }

  // Check that previously revealed secrets are still revealed
  for (const secret of previousSnapshot.worldState.revealedSecrets) {
    if (!currentSnapshot.worldState.revealedSecrets.includes(secret)) {
      issues.push({
        type: 'timeline_error',
        severity: 'warning',
        message: `秘密 "${secret}" 在之前的章节中被揭示，但在第 ${currentSnapshot.chapterNumber} 章未列出`,
        chapter: currentSnapshot.chapterNumber,
        details: { secret },
      });
    }
  }

  return issues;
}
