const {spawnSync} = require("child_process");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const result = spawnSync(
  "python",
  [
    "-m",
    "pytest",
    path.join(repoRoot, "tests", "test_command_center.py"),
    path.join(repoRoot, "tests", "test_skill_workshop.py"),
    "-q",
  ],
  {
    stdio: "inherit",
    cwd: repoRoot,
  },
);

if (typeof result.status === "number") {
  process.exit(result.status);
}
if (result.error) {
  throw result.error;
}
process.exit(1);
