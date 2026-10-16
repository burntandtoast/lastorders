
            JOB DESCRIPTION:
            {job.Description[..Math.Min(job.Description.Length, 4000)]}
            """;

        var requestBody = new
        {
            model = "gpt-4o",
            messages = new[]
            {
                new { role = "system", content = systemPrompt },
                new { role = "user", content = userMessage }
            },
            // was: model = "gpt-4-turbo"
