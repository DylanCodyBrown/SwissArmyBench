namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>A picture pasted into a message: its type (image/png...) and its bytes as base64. The body names it as
/// sab-image:new-1, new-2... in the order sent.</summary>
public sealed record CollabImage(string Type, string Data);
