namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/kernels: the kernel a document runs in (the project's one session, or its own).</summary>
public sealed record StartedKernel(string Kernel, string Python, SessionInfo? Session);
