namespace SwissArmyBench.Web.Pages.Grids.Steps;

/// <summary>What a step's form needs before it can be saved ("Tick at least one value."): shown in the form.</summary>
public sealed class StepFormException : Exception
{
    public StepFormException(string message)
        : base(message)
    {
    }
}
