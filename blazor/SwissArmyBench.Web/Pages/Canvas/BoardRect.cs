namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A rectangle on the board, in the page's pixels (the canvas file's own units).</summary>
public sealed record BoardRect(string Id, double Left, double Top, double Width, double Height)
{
    public double Right => Left + Width;

    public double Bottom => Top + Height;
}
