# Storage

Haversack's **Storage** page (in **Device**), on a handheld, shows how much space each game uses: the game, its Proton prefix, its shader cache and its saves. **Count disk use** lists the biggest first. Quit a game before changing anything here.

## Clear the shader cache

**Clear shader cache** frees the space Steam uses for a game's compiled shaders. Steam builds them again the next time the game runs, so the first minutes may stutter. Your saves are not touched.

## Reset a broken prefix and keep your saves

When a game stops starting because its Proton prefix is broken, **Reset prefix, keep saves** gives it a fresh one without losing your progress:

1. Haversack keeps a checked copy of the game's saves, then moves the prefix aside. Nothing is deleted.
2. Start the game once and quit at the title screen. Steam builds a fresh prefix.
3. When you quit, Haversack puts your saves back into the fresh prefix.
4. Once the game works, **Delete old prefix** frees the space of the old one.

Until step 3, **Undo reset** puts the old prefix back exactly as it was. Haversack will not reset a game that is installed inside its own prefix, because that would move the game itself.
