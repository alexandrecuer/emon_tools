"""
Dashboard Controller
"""
from datetime import datetime, timedelta
from sqlalchemy import case, and_
from sqlmodel import (
    Session,
    literal_column,
    select,
    func,
    union_all
)
from backend.controllers.base import BaseController
from backend.controllers.users import UserController
from backend.core.deps import CurrentUser
from backend.models.dashboard import (
    RangeActivityType,
    UsersActivity
)
from backend.models.db import (
    ArchiveFile,
    Category,
    DataPath,
    EmonHost,
    User
)
# pylint: disable=broad-exception-caught


class DashboardController:
    """
    Dashboard Controller
    """
    @staticmethod
    def get_range_activity(
        time_range: RangeActivityType
    ) -> tuple[int, int]:
        """
        Calculate the start and end datetime for a given time range.
        Args:
            time_range (RangeActivityType):
            The type of time range to calculate.
                It can be one of the following:
                - RangeActivityType.HOUR: The current hour.
                - RangeActivityType.DAY: The current day.
                - RangeActivityType.MONTH: The current month.
                - RangeActivityType.YEAR: The current year.
        Returns:
            tuple[Optional[int], Optional[int]]:
                A tuple containing the start and end datetime objects
                for the specified time range.
        Raises:
            ValueError: If an invalid time_range is provided.
        """
        now = datetime.now()
        if time_range == RangeActivityType.HOUR:
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=1)
        elif time_range == RangeActivityType.DAY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif time_range == RangeActivityType.MONTH:
            start = now.replace(
                day=1, hour=0, minute=0,
                second=0, microsecond=0
            )
            # Compute first day of next month
            if start.month == 12:
                end = start.replace(year=start.year+1, month=1)
            else:
                end = start.replace(month=start.month+1)
        elif time_range == RangeActivityType.YEAR:
            start = now.replace(
                month=1, day=1, hour=0, minute=0, second=0,
                microsecond=0
            )
            end = start.replace(year=start.year+1)
        else:
            raise ValueError(
                "Invalid time_range provided. "
                "Use 'hour', 'day', 'month', or 'year'."
            )
        return start, end

    @staticmethod
    def get_updates_count_by_model(
        *,
        session: Session,
        current_user: CurrentUser,
        time_range: RangeActivityType
    ) -> dict[str, int]:
        """
        Count the number of updates (rows with updated_at
        within the given time range) per model.
        If current_user.is_superuser is True, count across all rows;
        otherwise, only count rows where the model's
        user_id equals current_user.id. This data can be used to display
        a bar graph on the frontend.

        Args:
            session (Session): The database session.
            current_user (CurrentUser):
                The current user, with an is_superuser property.
            time_range (RangeActivityType): The time range to filter by.

        Returns:
            dict[str, int]:
                A dictionary mapping model names (as strings)
                to the number of updates.
        """
        start, end = DashboardController.get_range_activity(time_range)

        # list of tuples: (model, literal model name)
        models: list[tuple[type, str]] = [
            (User, "User"),
            (DataPath, "DataPath"),
            (EmonHost, "EmonHost"),
            (Category, "Category"),
            (ArchiveFile, "ArchiveFile")
        ]

        subqueries = []
        for model, model_name in models:
            # Build a subquery for each model
            # filtering on updated_at in the range.
            query = (
                select(literal_column(f"'{model_name}'").label("model"))
                .select_from(model)
                .where(model.updated_at >= start, model.updated_at < end)
            )
            # If the user is not a superuser,
            # add a filter to restrict to current user's rows.
            if not current_user.is_superuser:
                if model_name == 'User':
                    query = query.where(model.id == current_user.id)
                else:
                    query = query.where(model.owner_id == current_user.id)
            subqueries.append(query)

        # Combine all subqueries via UNION ALL.
        union_subq = union_all(*subqueries).subquery()

        # Group by model and count the number of rows per model.
        stmt = (
            select(
                union_subq.c.model,
                func.count().label("updates")  # pylint: disable=not-callable
            )
            .group_by(union_subq.c.model)
        )

        results = session.exec(stmt).all()
        # Convert the list of tuples into a dictionary.
        return [{"model": item[0], "value": item[1]} for item in results]

    @staticmethod
    def get_activity_count_by_model(
        *,
        session: Session,
        current_user: CurrentUser,
        time_range: RangeActivityType,
        is_current: bool = False
    ) -> list[dict[str, int]]:
        """
        Count, per model, the number of rows that have been updated
        (updated_at) and the number of rows that have been added
        (created_at) within the given time range.
        If current_user.is_superuser is True,
        counts are performed across all rows;
        otherwise, only rows where the model's
        user_id equals current_user.id are considered.
        This data is intended for a bar graph on the frontend.

        Returns:
            list[dict[str, int]]: A list of dictionaries, each with keys:
                - "model": the model name (e.g., "User")
                - "updated": count of rows with updated_at in the range
                - "added": count of rows with created_at in the range
        """
        start, end = DashboardController.get_range_activity(time_range)

        # list of tuples: (model, model name)
        models = [
            (User, "User"),
            (DataPath, "DataPath"),
            (EmonHost, "EmonHost"),
            (Category, "Category"),
            (ArchiveFile, "ArchiveFile")
        ]
        result = {
            'max': 0,
            'min': 0,
            'activity': []
        }
        for model, model_name in models:
            stmt = select(
                func.sum(
                    case(
                        (
                            and_(
                                model.updated_at >= start,
                                model.updated_at < end
                            ),
                            1
                        ),
                        else_=0
                    )
                ).label("updated"),
                func.sum(
                    case(
                        (
                            and_(
                                model.created_at >= start,
                                model.created_at < end
                            ),
                            1
                        ),
                        else_=0
                    )
                ).label("added")
            ).select_from(model)
            if not current_user.is_superuser or is_current is True:
                if model_name == 'User':
                    stmt = stmt.where(model.id == current_user.id)
                else:
                    stmt = stmt.where(model.owner_id == current_user.id)
            row = session.exec(stmt).first()
            updated_count = row.updated\
                if row and row.updated is not None else 0
            added_count = row.added if row and row.added is not None else 0
            result['activity'].append({
                "model": model_name,
                "updated": updated_count,
                "added": added_count
            })
            result['min'] = min(result['min'], updated_count, added_count)
            result['max'] = max(result['max'], updated_count, added_count)
        return result

    @staticmethod
    def get_dash_users_stats(
        session: Session,
        current_user: CurrentUser,
        time_range: RangeActivityType,
        is_current: bool = False
    ) -> UsersActivity:
        """
        Retrieves dashboard user statistics.

        Args:
            session (Session): The database session to use for queries.
            current_user (CurrentUser): The current authenticated user.
            is_current (bool, optional):
                Flag to determine if the current time range should be used.
                Defaults to False.

        Returns:
            ResponseModelBase:
                A response model containing the success status, data,
                and any error messages.

        Raises:
            HTTPException:
            If an unexpected error occurs, an HTTP 500 error is raised.

        Notes:
            - If the current user is a superuser,
              the total number of users is included in the response data.
            - The activity count by model is always included
              in the response data.
            - Handles various exceptions such as IntegrityError,
              ValidationError, ValueError, TypeError, and IOError.
        """
        try:
            nb_users, activity = 0, []
            if current_user.is_superuser:
                nb_users = UserController.count_users(
                    session=session
                )

            activity = DashboardController.get_activity_count_by_model(
                session=session,
                current_user=current_user,
                time_range=time_range,
                is_current=is_current
            )
            return UsersActivity(
                nb_users=nb_users,
                activity=activity
            )
        except Exception as ex:
            return BaseController.handle_exception(
                ex=ex,
                session=session
            )
