namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One library the project needs: its name, why (a short line: "data.ipynb and scripts/load.py") and its
/// status (waiting, installing, installed or failed).</summary>
public sealed record InstallPackage(string Name, string Why, string Status);
