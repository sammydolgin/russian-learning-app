---
name: quiz
description: Generate daily Russian vocabulary quiz from A0 level words
disable-model-invocation: false
allowed-tools: Read Edit
---

Generate a Russian vocabulary quiz following these steps:

1. **Read the current state** from `Russian-Learning.md`
2. **Select 10 words** following the rules:
   - Mix of new words (○ Not Yet Seen) and review words (↻ In Review)
   - Relatively random selection
   - Prioritize words that haven't been seen recently or have lower accuracy
3. **Present the quiz**:
   - Format: Russian word → user translates to English
   - Number each word 1-10
   - Wait for user to type their answers
4. **Check answers** after user responds
5. **Update Russian-Learning.md**:
   - Update vocabulary table (status, times seen, times correct, last seen date)
   - Update Current Progress section (%, accuracy, stats)
   - Add entry to Quiz History
   - Update Quick Stats
6. **Show results**:
   - Which answers were correct/incorrect
   - Summary stats (e.g., "8/10 correct")
   - Updated overall progress (% toward graduation)
   - Detailed breakdown of current status

Follow the system rules in Russian-Learning.md and MEMORY.md for all mechanics.
