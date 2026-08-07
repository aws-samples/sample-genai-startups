# Open SageMaker Studio

1. From the AWS Console, enter **SageMaker AI** in the Services search bar. Select **Amazon SageMaker AI** from the list.

![AWS Console services search for "SageMaker AI" with the Amazon SageMaker AI result highlighted above Amazon SageMaker and AWS Lake Formation](../../images/SageMakerSearch.png)

2. In the left navigation bar, select **Studio** under **Applications and IDEs**. Click **Open Studio**.

![SageMaker Studio landing page with SageMaker Studio highlighted under Applications and IDEs in the left nav, and the Open Studio button highlighted next to the workshop-user profile selector](../../images/OpenStudio.png)

3. In the upper left of the Studio environment, select **JupyterLab**.

![Studio Applications panel showing three tiles — JupyterLab, Code Editor, and MLflow — with the JupyterLab tile highlighted](../../images/JupyterLabSelect.png)

4. Click **Run** to start the pre-configured JupyterLab space.

![JupyterLab spaces list showing the SageMakerSpace space in Stopped status, with its Run button highlighted in the Action column](../../images/SpaceRun.png)

5. Once the space is running, click **Open** to launch JupyterLab.

![JupyterLab spaces list showing the SageMakerSpace space now in Running status, with its Open button highlighted next to the Stop button in the Action column](../../images/LaunchJupyterLabSpace.png)

6. JupyterLab opens with the workshop notebooks already available in the file browser on the left. You should see the following notebooks:

   - `00-setup.ipynb`
   - `01-data-preparation.ipynb`
   - `02-supervised-fine-tuning.ipynb`
   - `03-rlvr-training.ipynb`
   - `04-model-evaluation.ipynb`

::alert[If you don't see the notebooks, open a **Terminal** from the launcher and run: `aws s3 sync s3://slm-weights-$(aws sts get-caller-identity --query Account --output text)/ ~/`]{type="warning"}

![JupyterLab Launcher tab with the Terminal tile highlighted in the Other section, below the Notebook and Console sections](../../images/LaunchTerminal.png)

