---
name: progress
description: Show Russian language learning progress and statistics
disable-model-invocation: true
allowed-tools: Read
---

Generate a progress report from `Russian-Learning.md`:

1. **Read current state** from Russian-Learning.md
2. **Display comprehensive progress**:
   - Current level and overall completion percentage
   - Accuracy rate across all quizzes
   - Graduation status (how close to 90% accuracy + 50% coverage)
   - Quick stats (mastered, in review, not seen)
   - Current streak
3. **Show detailed breakdown**:
   - Words by status (✓ mastered, ↻ in review, ○ not seen)
   - Weak spots (words with low accuracy that need practice)
   - Recent quiz history
4. **Provide insights**:
   - What's going well
   - What needs focus
   - How many more quizzes estimated to graduation (if applicable)

Format output clearly with tables and bullet points for easy scanning.
